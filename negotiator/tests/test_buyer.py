import math

from negotiator import buyer as by
from negotiator import protocol as pr
from negotiator import table
from negotiator.buyer import Buyer

REQUEST = {"item": "bracket", "quantity": 100, "max_unit_price_eur": 4.80, "delivery_days": 21, "must_haves": []}


class Sim:
    """A test supplier modelled on the arena simulator (`arena_kit/sim.py` `_answer`): opens at `opening`, concedes
    `step` per buyer message down to a hidden `floor`, agrees when the buyer's price reaches its own, makes a final
    offer from `final_round`, and walks if pushed after that."""

    def __init__(self, opening, floor, step=0.10, final_round=5, delivery_days=14):
        self.price, self.floor, self.step, self.final_round = opening, floor, step, final_round
        self.delivery_days, self.round, self.status, self.n = delivery_days, 0, "open", 0

    def _sheet(self, price):
        self.n += 1
        return [{"term_sheet_id": f"s{self.n}", "terms": {"unit_price": round(price, 2), "quantity": 100,
                 "delivery_days": self.delivery_days, "payment_terms_days": 30, "terms": []}}]

    def respond(self, message):
        kind = message["type"]
        if kind == "rfq":
            return {"status": "open", "term_sheets": self._sheet(self.price), "body": "Our quote."}
        if kind == "accept":
            return {"status": "agreed", "confirmation": {"term_sheet_id": message["term_sheet_id"]}}
        if kind == "close":
            return None
        self.round += 1
        offer = message["terms"]["unit_price"]
        next_price = max(self.floor, round(self.price - self.step, 2))
        if offer >= next_price:
            self.price, self.status = offer, "agreed"
        elif self.status == "final_offer":
            self.status = "walked_away"
        else:
            self.price = next_price
            self.status = "final_offer" if self.round >= self.final_round else "open"
        return {"status": self.status, "term_sheets": self._sheet(self.price), "body": "Reply."}


def play(suppliers, request=REQUEST, **kw):
    return table.run(Buyer(request), suppliers, request, **kw)


def buyer_sends(out):
    return [(sid, m["terms"]["unit_price"], m["body"]) for sid, ev in out["threads"].items() for m in ev
            if m.get("type") == "send"]


def test_deal_with_three_suppliers_saves_against_the_winners_opening_quote():
    out = play({"A": Sim(5.40, 4.10), "B": Sim(5.10, 4.30), "C": Sim(5.80, 3.95, delivery_days=30)})
    assert out["outcome"] == "accepted"
    opening = pr.opening(out["threads"][out["supplier_id"]])[1]["unit_price"]
    assert out["terms"]["unit_price"] <= REQUEST["max_unit_price_eur"] and out["terms"]["unit_price"] < opening
    assert {e["source"] for e in out["trace"]} == {"buyer"}  # the table never had to correct the buyer


def test_no_deal_when_every_floor_is_above_the_cap():
    out = play({"A": Sim(5.60, 5.00), "B": Sim(5.50, 4.95)})
    assert out["outcome"] == "walked_away"
    assert all(p <= REQUEST["max_unit_price_eur"] for _, p, _ in buyer_sends(out))


def test_a_supplier_that_never_moves_off_its_opening_quote_cannot_win():
    request = {**REQUEST, "max_unit_price_eur": 5.50}
    out = play({"A": Sim(5.00, 5.00, step=0)}, request)
    assert out["outcome"] == "walked_away"


def test_one_cent_below_the_opening_quote_is_a_deal():
    request = {**REQUEST, "max_unit_price_eur": 5.50}
    out = play({"A": Sim(5.00, 4.99, step=0.01)}, request)
    assert out["outcome"] == "accepted" and out["terms"]["unit_price"] == 4.99


def test_a_deal_exactly_at_the_cap_is_accepted():
    out = play({"A": Sim(5.20, 4.80)})
    assert out["outcome"] == "accepted" and out["terms"]["unit_price"] == 4.80


def test_single_supplier_uses_the_ladder_without_auction_calls():
    out = play({"A": Sim(5.40, 4.20, step=0.15, final_round=8)})
    sends = buyer_sends(out)
    assert out["outcome"] == "accepted"
    assert sends[0][1] == math.floor(5.40 * by.ANCHOR * 100) / 100  # opening anchor
    assert not any("proceed with the other offer" in body for _, _, body in sends)


def test_ladder_counters_rise_monotonically_and_nothing_passes_the_cap():
    out = play({"A": Sim(5.40, 4.10), "B": Sim(5.10, 4.30), "C": Sim(5.30, 4.40)})
    assert all(p <= REQUEST["max_unit_price_eur"] for _, p, _ in buyer_sends(out))
    for sid in out["threads"]:
        # last calls may ask less than an earlier offer: a rival has beaten that offer since (reverse auction)
        ladder = [p for s, p, body in buyer_sends(out) if s == sid and "proceed with the other offer" not in body]
        assert ladder == sorted(ladder)


def test_a_final_offer_is_never_countered_and_walkers_stay_out():
    out = play({"A": Sim(5.40, 4.70, step=0.05, final_round=1), "B": Sim(5.20, 4.75, step=0.05, final_round=2)})
    for sid, events in out["threads"].items():
        after_final = False
        for m in events:
            if m.get("from") == sid and m.get("status") == "final_offer":
                after_final = True
            elif after_final:
                assert m.get("type") in ("accept", "close") or m.get("from") == sid
    assert {e["source"] for e in out["trace"]} == {"buyer"}


def test_the_reverse_auction_beats_the_best_single_supplier_result():
    sims = lambda: {"A": Sim(5.40, 3.90, step=0.15, final_round=8), "B": Sim(5.30, 4.00, step=0.15, final_round=8)}  # noqa: E731
    together = play(sims())
    alone = [play({sid: sim})["terms"]["unit_price"] for sid, sim in sims().items()]
    assert together["outcome"] == "accepted"
    assert together["terms"]["unit_price"] < min(alone)
    assert any("proceed with the other offer" in body for _, _, body in buyer_sends(together))


def test_rival_claims_say_offered_never_agreed():
    out = play({"A": Sim(5.40, 4.10), "B": Sim(5.10, 4.30), "C": Sim(5.30, 4.40)})
    bodies = [body for _, _, body in buyer_sends(out)]
    assert any("has offered EUR" in b for b in bodies)
    assert not any("agreed" in b for b in bodies)


def test_ineligible_supplier_gets_no_counters():
    out = play({"A": Sim(5.40, 4.10, step=0.15, final_round=8), "C": Sim(4.00, 3.00, delivery_days=30)})
    assert not [s for s, _, _ in buyer_sends(out) if s == "C"]
    assert out["supplier_id"] == "A"


def test_same_replies_give_the_same_moves():
    run = lambda: play({"A": Sim(5.40, 4.10), "B": Sim(5.10, 4.30)})  # noqa: E731
    first, second = run(), run()
    strip = lambda out: [{k: v for k, v in e.items() if k != "seconds"} for e in out["trace"]]  # noqa: E731
    assert strip(first) == strip(second)
