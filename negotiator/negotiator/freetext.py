"""Suppliers that speak prose instead of the protocol, behind an adapter the table cannot tell from a protocol supplier.

`FreeTextAdapter` is the only part the table sees. On the way out it renders the buyer's message as text (the
writer rephrases price offers); the counterpart answers in prose; on the way back the reader turns that prose into
a protocol reply, or `no_bid`. `table.py` and `buyer.py` do not change: every price still comes from the buyer and
every accept still passes the table's checks. A free-text supplier cannot sign, so its confirmation is what the
reader read from its prose, with no signature.

`ProseSupplier` is the demo counterpart: a simulated `Supplier` persona (hidden floor and concession curve kept)
whose replies keep only the wording, with seeded variation, and drop the term sheets. It reads the buyer's price
from the structured message, as a stand-in for reading the writer's text, which always states that price.
Its floor stays on the inner `Supplier`; no prompt, thread or result ever sees it.
"""

import random
import re

from . import reader, writer

GREETINGS = ("", "Hello,", "Dear buyer,", "Good morning,", "Thanks for your message.")
SIGN_OFFS = ("", "Best regards.", "Kind regards, sales team.", "Let us know if you have questions.")
PRICE = re.compile(r"EUR (\d+)\.(\d\d)")
PRICE_STYLES = ("EUR {w}.{c}", "€{w}.{c}", "{w}.{c} EUR", "EUR {w},{c}")
EUR_AMOUNT = re.compile(r"EUR (\d+\.\d\d)")


class ProseSupplier:
    """A simulated supplier persona that answers in prose only."""

    def __init__(self, supplier, seed):
        self.inner = supplier
        self.rng = random.Random(f"prose|{seed}|{supplier.persona.sid}")  # its own stream: the run's rng is untouched

    def _vary(self, text):
        style = self.rng.choice(PRICE_STYLES)
        text = PRICE.sub(lambda m: style.format(w=m.group(1), c=m.group(2)), text)
        return " ".join(p for p in (self.rng.choice(GREETINGS), text, self.rng.choice(SIGN_OFFS)) if p)

    def reply(self, message, text):
        """Prose answer to the buyer's message (`text` is what the buyer wrote), or None after a close."""
        kind = message["type"]
        if kind == "accept":  # the adapter says whether the buyer took the supplier's latest offer
            message = {"type": "accept", "term_sheet_id": self.inner.last_sheet if message["current"] else None}
        out = self.inner.respond(message)
        if out is None:
            return None
        conf = out.get("confirmation")
        prose = conf["text"] if conf else out["body"]
        if kind == "rfq":
            prose += " Included: " + ", ".join(self.inner.persona.terms) + "."
        return self._vary(prose)


class FreeTextAdapter:
    """The protocol side of a prose-speaking supplier: `respond(message) -> protocol reply`, like `Supplier`."""

    def __init__(self, sid, name, counterpart, client, request):
        self.sid, self.name, self.counterpart, self.client, self.request = sid, name, counterpart, client, request
        self.sheets, self.last_sheet, self.last_terms = 0, None, None

    def _text(self, message):
        """The buyer's message as text, and the writer's verdict. Code writes every text but the price offers."""
        kind, request = message["type"], self.request
        if kind == "rfq":
            return (f"Request for quote: {request['quantity']} x {request['item']}, delivery within "
                    f"{request['delivery_days']} days. Please send your unit price in EUR."), None
        if kind == "accept":
            return f"We accept your offer {message['term_sheet_id']}. Please confirm the order.", None
        if kind == "close":
            return "Thank you for your offer. We will not proceed with you.", None
        body, price = message.get("body", ""), message["terms"]["unit_price"]
        rivals = [float(p) for p in EUR_AMOUNT.findall(body) if abs(float(p) - price) > 1e-9]
        return writer.write(self.client, body, price=price, rival=rivals[0] if rivals else None,
                            quantity=message["terms"]["quantity"], delivery_days=message["terms"]["delivery_days"])

    def respond(self, message):
        kind = message.get("type")
        sent, _ = self._text(message)
        if kind == "close":
            self.counterpart.reply(message, sent)
            return None
        if kind == "accept":
            raw = self.counterpart.reply({"type": "accept", "current": message.get("term_sheet_id") == self.last_sheet},
                                         sent)
            return self._confirmation(message, raw, sent)
        raw = self.counterpart.reply(message, sent)
        self.sheets += 1
        sheet_id = f"FT-{self.sid}-{self.sheets}"
        buyer_message = message if kind == "rfq" else {**message, "body": sent}
        msg, reason = reader.read(self.client, raw, buyer_message=buyer_message, previous_terms=self.last_terms,
                                  sheet_id=sheet_id, quantity=self.request["quantity"])
        if msg["term_sheets"]:
            self.last_sheet, self.last_terms = sheet_id, msg["term_sheets"][0]["terms"]
        return {**msg, "raw_text": raw or "", "sent_text": sent, **({"read_error": reason} if reason else {})}

    def _confirmation(self, message, raw, sent):
        figures, reason = reader.read_confirmation(self.client, raw, accepted_text=sent)
        audit = {"raw_text": raw or "", "sent_text": sent, **({"read_error": reason} if reason else {})}
        if figures is None:
            return {"status": "no_bid", "term_sheets": [], "body": raw or "(no reply)", **audit}
        sheet_id = message["term_sheet_id"]
        confirmation = {"supplier_id": self.sid, "supplier": self.name, "quote_id": f"{sheet_id}-confirmation",
                        "term_sheet_id": sheet_id, "unit_price": figures["unit_price"], "quantity": figures["quantity"],
                        "total": figures["total"], "currency": "EUR", "delivery_days": figures["delivery_days"],
                        "payment_terms_days": figures["payment_terms_days"],
                        "terms": list((self.last_terms or {}).get("terms", [])), "text": raw, "channel": "free_text"}
        return {"status": "agreed", "term_sheets": [], "body": raw, "confirmation": confirmation, **audit}
