"""Suppliers played by NegMAS negotiation strategies: independent strategies, our reservation prices.

Each supplier runs one NegMAS single-issue (price) SAO negotiation with a stock seller strategy that this team did
not write: Boulware (concedes late), Conceder (concedes early) and naive tit-for-tat (mirrors our concessions).
We still choose each seller's reservation price and price range, so this tests the buyer against strategies we did
not design, not against preferences we did not choose.

Our buyer acts in the NegMAS buyer seat through `SAOMechanism.step(action)`, one offer per step: an RFQ runs the
seller's opening step; a counter runs our step and then the seller's; an accept is our ACCEPT_OFFER step. To the
table these suppliers look exactly like the simulated ones: `respond(message) -> reply` in the protocol.

Dev-only: needs `negmas` (see `negotiator/requirements-dev.txt`). Not imported unless `--suppliers negmas`.
"""

import hashlib
import warnings

from . import signing
from .protocol import ROUND_LIMIT

BROKEN_TOTAL_DELTA_EUR = 100.0
MAX_GRID = 20000  # seller price points; above this the seller's own offers use a coarser grid (ours stay exact)
STRATEGIES = (("A", "Boulware seller", "BoulwareTBNegotiator"), ("B", "Conceder seller", "ConcederTBNegotiator"),
              ("C", "Tit-for-tat seller", "NaiveTitForTatNegotiator"))
MODEL = "negmas: independent strategies, our reservation prices"


class NegmasSupplier:
    def __init__(self, sid, name, strategy, request, floor_eur, opening_eur, seed, scenario, persona):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from negmas import make_issue, sao
            from negmas.outcomes import make_os
            from negmas.preferences import LinearAdditiveUtilityFunction
            from negmas.preferences.value_fun import AffineFun
        self.sid, self.name, self.request, self.seed, self.persona = sid, name, request, seed, persona
        self._floor = floor_eur  # the reservation price we chose; never sent to the buyer
        self.broken = scenario == "broken_quote"
        # every NegMAS seller meets the deadline, so all three strategies compete on price
        self.delivery_days = max(1, request["delivery_days"] + min(0, persona.delivery_offset))
        self._key = signing.key_from_seed(seed, f"negmas-{sid}")
        lo, hi = max(1, round(floor_eur * 50)), max(round(floor_eur * 100) + 1, round(opening_eur * 100))  # cents
        step = max(1, -(-(hi - lo) // MAX_GRID))
        values = list(range(lo, hi + 1, step)) if step > 1 else (lo, hi)
        issues = [make_issue(values, "price")]
        space = make_os(issues)
        span = hi - lo
        seller_u = LinearAdditiveUtilityFunction(values={"price": AffineFun(1 / span, -lo / span)}, outcome_space=space,
                                                 reserved_value=(round(floor_eur * 100) - lo) / span)
        buyer_u = LinearAdditiveUtilityFunction(values={"price": AffineFun(-1 / span, hi / span)}, outcome_space=space)
        # time-based strategies pace themselves by n_steps: two steps (ours and theirs) per buyer message
        self._m = sao.SAOMechanism(issues=issues, n_steps=2 * ROUND_LIMIT + 2, one_offer_per_step=True)
        self._seller, self._buyer = getattr(sao, strategy)(name=f"{sid}-seller"), sao.ToughNegotiator(name=f"{sid}-buyer")
        self._m.add(self._seller, preferences=seller_u)
        self._m.add(self._buyer, preferences=buyer_u)
        self._resp = sao.SAOResponse
        from negmas.gb.common import ResponseType
        self._rt = ResponseType
        self.sheets, self.last_sheet, self.price, self.status = 0, None, None, "open"

    @property
    def public_key(self):
        return signing.public_hex(self._key)

    def _step(self, action=None):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return self._m.step({self._buyer.id: action} if action else None)

    def _terms(self, price):
        return {"unit_price": price, "quantity": self.request["quantity"], "delivery_days": self.delivery_days,
                "payment_terms_days": self.persona.payment_terms_days, "terms": list(self.persona.terms)}

    def _sheet(self, price, status, body):
        self.price, self.status = round(price / 100, 2), status
        self.sheets += 1
        self.last_sheet = f"{self.sid}-{self.sheets}"
        return {"status": status, "term_sheets": [{"term_sheet_id": self.last_sheet, "terms": self._terms(self.price)}],
                "body": body}

    def respond(self, message):
        kind = message.get("type")
        if kind == "close":
            return None
        if kind == "rfq":
            state = self._step()
            return self._sheet(state.current_offer[0], "open", f"Our offer: EUR {state.current_offer[0] / 100:.2f} per unit.")
        if kind == "accept":
            if message.get("term_sheet_id") != self.last_sheet or self.status == "walked_away":
                return {"status": self.status, "term_sheets": [], "body": "That offer is no longer open."}
            if self._m.state.agreement is None:
                state = self._step(self._resp(self._rt.ACCEPT_OFFER, (round(self.price * 100),)))
                if state.agreement is None:
                    return {"status": "walked_away", "term_sheets": [], "body": "No agreement was reached."}
            self.status = "agreed"
            return {"status": "agreed", "term_sheets": [], "body": "Order confirmed.", "confirmation": self.confirm()}
        offer = round(((message.get("terms") or {}).get("unit_price") or 0) * 100)
        self._step(self._resp(self._rt.REJECT_OFFER, (offer,)))  # our counter, in the buyer seat
        state = self._step()  # the seller's turn: accept our counter, or counter itself
        if state.agreement is not None:
            return self._sheet(state.agreement[0], "agreed", f"Agreed at EUR {state.agreement[0] / 100:.2f} per unit.")
        if not state.running or state.current_offer is None:
            self.status = "walked_away"
            return {"status": "walked_away", "term_sheets": [], "body": "We are ending this negotiation."}
        return self._sheet(state.current_offer[0], "open", f"We can do EUR {state.current_offer[0] / 100:.2f} per unit.")

    def confirm(self):
        qty = self.request["quantity"]
        total = round(self.price * qty, 2) + (BROKEN_TOTAL_DELTA_EUR if self.broken else 0.0)
        quote_id = f"Q-N{self.sid}-" + hashlib.sha256(f"{self.name}|{self.price}|{qty}|{self.seed}".encode()).hexdigest()[:10]
        body = {"supplier_id": self.sid, "supplier": self.name, "quote_id": quote_id, "term_sheet_id": self.last_sheet,
                "unit_price": self.price, "quantity": qty, "total": round(total, 2), "currency": "EUR",
                "delivery_days": self.delivery_days, "payment_terms_days": self.persona.payment_terms_days,
                "terms": list(self.persona.terms),
                "text": f"{self.name} confirms order {quote_id}: {qty} x {self.request['item']} at EUR {self.price:.2f} "
                        f"per unit (total EUR {round(total, 2):.2f})."}
        return signing.sign(self._key, body)


def build(request, rng, scenario, seed, personas):
    """Three NegMAS suppliers. Reservation floors are drawn like the simulated suppliers' (ours to choose); the
    opening ceiling comes from each persona's markup."""
    import numpy

    numpy.random.seed(seed)  # some NegMAS strategies draw from numpy; a seeded run must reproduce
    cap = request["max_unit_price_eur"]
    out = {}
    for (sid, name, strategy), persona in zip(STRATEGIES, personas):
        floor = round(cap * (rng.uniform(1.04, 1.15) if scenario == "above_cap" else rng.uniform(0.78, 0.95)), 2)
        opening = round(floor * (1 + persona.markup + rng.uniform(0, 0.05)), 2)
        out[sid] = NegmasSupplier(sid, name, strategy, request, floor, opening, seed, scenario, persona)
    return out
