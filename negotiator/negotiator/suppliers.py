"""Three simulated supplier agents. Each has a hidden price floor, its own concession schedule and wording, and
signs its order confirmation. They speak the protocol in `protocol.py` and nothing else reaches the buyer.

Behaviour modelled on the upstream supplier gym and arena simulator
(https://github.com/Jaseelkt007/tacto-buyer-agent, `arena_kit/supplier_gym/policy.py` `Profile` and `menu`,
`arena_kit/sim.py` `_answer`; MIT, Copyright (c) 2026 Tacto Technology GmbH): open at a markup above the floor,
shrink the markup toward a final markup as rounds pass, agree when the buyer reaches the next price, make a final
offer from a set round, and walk away if pushed after it.
"""

import hashlib
import math
from dataclasses import dataclass

from . import signing

BROKEN_TOTAL_DELTA_EUR = 100.0


def cents_up(x):
    return math.ceil(x * 100 - 1e-9) / 100


def cents_down(x):
    return math.floor(x * 100 + 1e-9) / 100


@dataclass(frozen=True)
class Persona:
    sid: str
    name: str
    markup: float  # opening price = floor * (1 + markup + seeded jitter)
    final_markup: float  # the markup it ends at in its final round
    power: float  # concession curve: below 1 it concedes early, above 1 late
    final_round: int  # from this round on its offer is final
    delivery_offset: int  # days relative to the requested deadline
    payment_terms_days: int
    terms: tuple
    opening: str
    move: str
    hold: str
    final: str
    agree: str
    walk: str
    confirm: str


PERSONAS = (
    Persona(
        sid="A", name="Supplier A", markup=0.22, final_markup=0.03, power=1.0, final_round=6,
        delivery_offset=-3, payment_terms_days=30,
        terms=("certificate of conformity", "DAP delivery", "ISO 9001 certified"),
        opening="Thank you for the enquiry. For {qty} x {item} we can quote EUR {price:.2f} per unit, "
        "delivery in {days} days, payment net {pay}.",
        move="We have reviewed our costs again. Our improved price is EUR {price:.2f} per unit.",
        hold="EUR {price:.2f} per unit is already our lowest price for this order.",
        final="Our final offer is EUR {price:.2f} per unit.",
        agree="We can agree to EUR {price:.2f} per unit. Please confirm your order.",
        walk="Our final offer was not accepted. We are ending this discussion.",
        confirm="{supplier} confirms order {quote_id}: {qty} x {item} at EUR {price:.2f} per unit "
        "(total EUR {total:.2f}), delivery in {days} days, payment net {pay}.",
    ),
    Persona(
        sid="B", name="Supplier B", markup=0.15, final_markup=0.05, power=0.6, final_round=4,
        delivery_offset=0, payment_terms_days=45,
        terms=("material certificate 3.1", "free shipping", "ISO 9001 certified"),
        opening="Hello, happy to help. Our offer: EUR {price:.2f}/unit for {qty} pieces of {item}. "
        "Lead time {days} days, terms net {pay}, shipping included.",
        move="To win this order we can go to EUR {price:.2f}/unit.",
        hold="Sorry, we cannot go below EUR {price:.2f}/unit.",
        final="EUR {price:.2f}/unit is our final offer.",
        agree="Agreed at EUR {price:.2f}/unit. Send us the order.",
        walk="We cannot continue on these terms. Goodbye.",
        confirm="Order {quote_id} confirmed by {supplier}. {qty} pcs {item}, EUR {price:.2f}/unit, "
        "EUR {total:.2f} total, lead time {days} days, net {pay}.",
    ),
    Persona(
        sid="C", name="Supplier C", markup=0.3, final_markup=0.02, power=1.6, final_round=8,
        delivery_offset=5, payment_terms_days=14,
        terms=("standard packaging",),
        opening="Quote for {item}, quantity {qty}: unit price EUR {price:.2f}. "
        "Earliest dispatch in {days} days. Payment within {pay} days.",
        move="Revised quote: EUR {price:.2f} per unit.",
        hold="The price stays at EUR {price:.2f} per unit.",
        final="Final quote: EUR {price:.2f} per unit.",
        agree="Accepted at EUR {price:.2f} per unit.",
        walk="Negotiation closed.",
        confirm="Confirmation {quote_id} from {supplier}: {qty} units of {item} at EUR {price:.2f}, "
        "total EUR {total:.2f}, dispatch in {days} days, payment within {pay} days.",
    ),
)


class Supplier:
    """One simulated supplier. The floor, markups and `scenario` stay on this object; the table only passes its
    replies on, cleaned to protocol fields."""

    def __init__(self, persona, request, rng, scenario, seed, quote=None):
        cap = request["max_unit_price_eur"]
        self.persona, self.request, self.seed = persona, request, seed
        self.name = quote["name"] if quote else persona.name
        self.broken = scenario == "broken_quote"
        if quote:  # real opening price: no rng draws, floor from the persona's markup
            self.price = cents_up(quote["unit_price_eur"])
            self._floor = max(0.01, cents_down(self.price / (1 + persona.markup)))  # a 1-cent quote must not floor at 0
        else:
            floor_ratio = rng.uniform(1.04, 1.15) if scenario == "above_cap" else rng.uniform(0.78, 0.95)
            self._floor = cents_up(cap * floor_ratio)
            self.price = cents_up(self._floor * (1 + persona.markup + rng.uniform(0, 0.05)))
        self._open_markup = self.price / self._floor - 1
        self.delivery_days = max(1, request["delivery_days"] + persona.delivery_offset)
        self._key = signing.key_from_seed(seed, persona.sid)
        self.round, self.status, self.sheets = 0, "open", 0
        self.last_sheet = None

    @property
    def public_key(self):
        return signing.public_hex(self._key)

    def _fill(self, template, price, **extra):
        return template.format(item=self.request["item"], qty=self.request["quantity"], price=price,
                               days=self.delivery_days, pay=self.persona.payment_terms_days, **extra)

    def _terms(self, price):
        return {"unit_price": price, "quantity": self.request["quantity"], "delivery_days": self.delivery_days,
                "payment_terms_days": self.persona.payment_terms_days, "terms": list(self.persona.terms)}

    def _reply(self, text):
        self.sheets += 1
        self.last_sheet = f"{self.persona.sid}-{self.sheets}"
        return {"status": self.status, "term_sheets": [{"term_sheet_id": self.last_sheet, "terms": self._terms(self.price)}],
                "body": self._fill(text, self.price)}

    def next_price(self):
        """Its price after this round: the markup shrinks from its opening toward its final markup
        (`supplier_gym.policy.SupplierPolicy.menu`), never below the floor and never back up."""
        p = self.persona
        remaining = max(0.0, 1 - self.round / p.final_round)
        markup = p.final_markup + (self._open_markup - p.final_markup) * remaining ** p.power
        return min(self.price, max(self._floor, cents_up(self._floor * (1 + markup))))

    def respond(self, message):
        kind = message.get("type")
        if kind == "rfq":
            return self._reply(self.persona.opening)
        if kind == "accept":
            if message.get("term_sheet_id") != self.last_sheet or self.status == "walked_away":
                return {"status": self.status, "term_sheets": [], "body": "That offer is no longer open."}
            self.status = "agreed"
            return {"status": "agreed", "term_sheets": [], "body": "Order confirmed.", "confirmation": self.confirm()}
        if kind == "close":
            return None
        self.round += 1
        offer = (message.get("terms") or {}).get("unit_price") or 0
        target = self.next_price()
        if offer >= target and offer >= self._floor:  # `sim._answer`: the buyer reached its price
            self.price, self.status = cents_up(offer), "agreed"
            return self._reply(self.persona.agree)
        if self.status == "final_offer":  # pushed after its final offer
            self.status = "walked_away"
            return {"status": "walked_away", "term_sheets": [], "body": self.persona.walk}
        moved = target < self.price
        self.price = target
        if self.round >= self.persona.final_round:
            self.status = "final_offer"
            return self._reply(self.persona.final)
        self.status = "open"
        return self._reply(self.persona.move if moved else self.persona.hold)

    def confirm(self):
        """The signed order confirmation for its current price. With `broken_quote` its total is wrong, while the
        signature over that wrong total still verifies: the checker must catch the mismatch itself."""
        qty = self.request["quantity"]
        total = round(self.price * qty, 2) + (BROKEN_TOTAL_DELTA_EUR if self.broken else 0.0)
        digest = hashlib.sha256(f"{self.name}|{self.price}|{qty}|{self.seed}".encode())
        quote_id = f"Q-{self.persona.sid}-{digest.hexdigest()[:10]}"
        body = {
            "supplier_id": self.persona.sid,
            "supplier": self.name,
            "quote_id": quote_id,
            "term_sheet_id": self.last_sheet,
            "unit_price": self.price,
            "quantity": qty,
            "total": round(total, 2),
            "currency": "EUR",
            "delivery_days": self.delivery_days,
            "payment_terms_days": self.persona.payment_terms_days,
            "terms": list(self.persona.terms),
            "text": self._fill(self.persona.confirm, self.price, supplier=self.name, quote_id=quote_id, total=round(total, 2)),
        }
        return signing.sign(self._key, body)
