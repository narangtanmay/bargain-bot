"""A fake model for end-to-end tests: it answers the reader, confirmation and writer prompts by parsing the simulated
suppliers' wording with regexes, so a free-text run needs no network. It knows the personas' phrasing, nothing else."""

import json
import re

from negotiator import reader, writer

AMOUNT = re.compile(r"(?:EUR ?\d+[.,]\d\d|€\d+[.,]\d\d|\d+[.,]\d\d EUR)")
DELIVERY = re.compile(r"(?:delivery in|lead time|dispatch in) (\d+) days", re.I)
PAYMENT = re.compile(r"\b(?:net (\d+)|within (\d+) days)")
QUANTITY = re.compile(r"\b(\d+) (?:x|pcs|units)\b")
INCLUDED = re.compile(r"Included: (.*?)\.(?:\s|$)")


def value(snippet):
    return reader.parse_number(re.search(r"\d+[.,]?\d*", snippet).group(0))


def fig(match, group=0):
    if not match:
        return None
    number = next(g for g in match.groups() if g) if group else None
    return {"value": int(number) if number else value(match.group(0)), "quote": match.group(0)}


def supplier_text(user):
    return user.split("<<<\n", 1)[1].rsplit("\n>>>", 1)[0]


def read_reply(text):
    low = text.lower()
    if re.search(r"ending this discussion|cannot continue|negotiation closed", low):
        return {"status": "walked_away"}
    status = "final_offer" if "final" in low else "agreed" if re.search(r"\b(agree|agreed|accepted)\b", low) else "open"
    price = AMOUNT.search(text)
    included = INCLUDED.search(text)
    return {"status": status, "unit_price": {"value": value(price.group(0)), "quote": price.group(0)} if price else None,
            "quantity": None, "delivery_days": fig(DELIVERY.search(text), 1),
            "payment_terms_days": fig(PAYMENT.search(text), 1),
            "terms": included.group(1).split(", ") if included else []}


def read_confirmation(text):
    unit = total = None
    for m in AMOUNT.finditer(text):
        before, after = text[max(0, m.start() - 6):m.start()], text[m.end():m.end() + 6]
        if before.lower() == "total ":
            total = {"value": value(m.group(0)), "quote": before + m.group(0)}
        elif after.lower() == " total":
            total = {"value": value(m.group(0)), "quote": m.group(0) + after}
        elif unit is None:
            unit = {"value": value(m.group(0)), "quote": m.group(0)}
    return {"confirmed": True, "unit_price": unit, "quantity": fig(QUANTITY.search(text), 1), "total": total,
            "delivery_days": fig(DELIVERY.search(text), 1), "payment_terms_days": fig(PAYMENT.search(text), 1)}


class Oracle:
    """Provider for `llm.Client`. `rewrite(body) -> text` sets what the writer answers; `prompts` keeps every call."""

    model = "oracle"

    def __init__(self, rewrite=lambda body: "Many thanks for your quote. " + body):
        self.rewrite, self.prompts = rewrite, []

    def complete(self, system, user, *, max_tokens, timeout_s):
        self.prompts.append((system, user))
        if system == writer.SYSTEM:
            text = self.rewrite(supplier_text(user))
        elif system == reader.CONFIRM_SYSTEM:
            text = json.dumps(read_confirmation(supplier_text(user)))
        else:
            text = json.dumps(read_reply(supplier_text(user)))
        return text, {"input_tokens": len(user.split()), "output_tokens": len(text.split())}
