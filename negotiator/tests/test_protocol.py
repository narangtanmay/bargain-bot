import ast
import hashlib
import json
from pathlib import Path

from negotiator import protocol as pr
from negotiator import table
from negotiator.buyer import Buyer, accept_gate, closing_move

ROOT = Path(__file__).resolve().parent.parent
REQUEST = {"item": "bracket", "quantity": 100, "max_unit_price_eur": 4.80, "delivery_days": 21, "must_haves": []}


def terms(price, **extra):
    return {"unit_price": price, "quantity": 100, "delivery_days": 14, "payment_terms_days": 30, "terms": [], **extra}


class Scripted:
    """A test supplier: a list of prices, one per buyer message; agrees to whatever it is accepted on."""

    def __init__(self, prices, status="open", extra=None):
        self.prices, self.status, self.extra, self.seen, self.n = list(prices), status, extra or {}, [], 0

    def respond(self, message):
        self.seen.append(message)
        if message["type"] == "accept":
            return {"status": "agreed", "confirmation": {"term_sheet_id": message["term_sheet_id"]}}
        if message["type"] == "close":
            return None
        price = self.prices[min(self.n, len(self.prices) - 1)]
        self.n += 1
        return {"status": self.status, "term_sheets": [{"term_sheet_id": f"s{self.n}", "terms": terms(price)}],
                "body": f"EUR {price:.2f}", **self.extra}


class Script:
    """A test buyer that plays a fixed list of moves, each a function of the threads."""

    def __init__(self, *moves):
        self.moves = list(moves)

    def decide(self, threads):
        return self.moves.pop(0)(threads)


def send(sid, price):
    return lambda threads: {"supplier_id": sid, "type": "send", "terms": terms(price), "body": "", "why": "test"}


def accept(sid):
    return lambda threads: {"supplier_id": sid, "type": "accept", "term_sheet_id": pr.standing(threads[sid])[0],
                            "why": "test"}


# ---------- protocol ----------

def test_terms_validation_rejects_missing_negative_bool_and_nonfinite_prices():
    assert pr.validate_terms(terms(4.5)) == []
    assert pr.validate_terms({**terms(4.5), "unit_price": None})
    assert pr.validate_terms(terms(-1))
    assert pr.validate_terms(terms(True))
    assert pr.validate_terms(terms(float("nan")))
    assert pr.validate_terms({**terms(4.5), "quantity": 0})


def test_supplier_message_is_cleaned_to_known_fields_and_statuses():
    msg = pr.clean_supplier_message("A", {"status": "open", "term_sheets": [{"term_sheet_id": "s1", "terms": terms(4.5)}],
                                          "body": "hi", "floor": 3.1, "from": "B"})
    assert msg == {"from": "A", "status": "open", "term_sheets": [{"term_sheet_id": "s1", "terms": terms(4.5)}],
                   "body": "hi"}
    assert pr.clean_supplier_message("A", {"status": "bribed", "term_sheets": []})["status"] == "no_bid"
    assert pr.clean_supplier_message("A", {"status": "open", "term_sheets": [{"term_sheet_id": "s1",
                                                                              "terms": terms(-2)}]})["status"] == "no_bid"
    assert pr.clean_supplier_message("A", "not a dict")["status"] == "no_bid"


def test_buyer_module_imports_nothing_from_the_supplier_side():
    tree = ast.parse((ROOT / "negotiator" / "buyer.py").read_text())
    names = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    names += [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    names += [a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names]
    assert not [x for x in names if "supplier" in x or x == "engine"]


# ---------- accept gate and closing move ----------

def test_accept_gate_needs_cap_and_a_price_strictly_below_the_opening_quote():
    assert accept_gate(REQUEST, terms(4.70), opening=5.00)[0]
    assert accept_gate(REQUEST, terms(4.80), opening=5.00)[0]  # the cap is inclusive
    assert not accept_gate(REQUEST, terms(4.81), opening=5.00)[0]
    assert not accept_gate(REQUEST, terms(4.60), opening=4.60)[0]  # no saving, no deal
    assert accept_gate(REQUEST, terms(4.59), opening=4.60)[0]
    assert not accept_gate(REQUEST, terms(4.50, delivery_days=30), opening=5.00)[0]
    assert not accept_gate(REQUEST, terms(4.50, quantity=99), opening=5.00)[0]


def test_closing_move_takes_the_cheapest_acceptable_standing_sheet_else_walks():
    def thread(*prices, **extra):
        out = [{"from": "buyer", "type": "rfq"}]
        for i, p in enumerate(prices):
            out.append({"from": "S", "status": "open", "term_sheets": [{"term_sheet_id": f"s{i}", "terms": terms(p, **extra)}]})
        return out

    threads = {"A": thread(5.00, 4.70), "B": thread(4.60, 4.60), "C": thread(5.00, 4.50, delivery_days=30)}
    move = closing_move(REQUEST, threads)
    assert (move["type"], move["supplier_id"], move["term_sheet_id"]) == ("accept", "A", "s1")
    assert closing_move(REQUEST, {"B": thread(4.60, 4.60)})["type"] == "walk_away"


# ---------- table ----------

def test_table_runs_rfq_counter_accept_with_one_trace_entry_per_decision():
    sup = {"A": Scripted([5.00, 4.50]), "B": Scripted([5.20])}
    out = table.run(Script(send("A", 4.00), accept("A")), sup, REQUEST)
    assert out["outcome"] == "accepted" and out["supplier_id"] == "A" and out["terms"]["unit_price"] == 4.50
    assert out["confirmation"] == {"term_sheet_id": "s2"}
    assert [e["action"] for e in out["trace"]] == ["send", "accept"]
    assert [e["source"] for e in out["trace"]] == ["buyer", "buyer"]
    assert sup["B"].seen[-1]["type"] == "close"  # the losing thread is closed
    assert out["log_hash"] == hashlib.sha256(table.canonical({"threads": out["threads"], "trace": out["trace"]})).hexdigest()


def test_buyer_never_sees_supplier_internals_and_cannot_mutate_supplier_state():
    seen = []

    class Peek:
        def decide(self, threads):
            seen.append(json.dumps(threads))
            threads["A"][-1]["term_sheets"][0]["terms"]["unit_price"] = 0.01  # tampering with its own copy only
            return {"supplier_id": "A", "type": "walk_away", "why": "test"}

    out = table.run(Peek(), {"A": Scripted([5.00], extra={"floor": 3.1, "markup": 0.2})}, REQUEST)
    assert "floor" not in seen[0] and "markup" not in seen[0]
    assert out["threads"]["A"][1]["term_sheets"][0]["terms"]["unit_price"] == 5.00


def test_engine_error_falls_back_to_the_closing_move():
    class Broken:
        def decide(self, threads):
            raise RuntimeError("bug")

    out = table.run(Broken(), {"A": Scripted([5.00])}, REQUEST)
    assert out["outcome"] == "walked_away"
    assert out["trace"][-1]["source"] == "fallback" and "RuntimeError" in out["trace"][-1]["why"]


def test_invalid_action_falls_back_to_the_closing_move():
    bad = lambda threads: {"supplier_id": "A", "type": "accept", "term_sheet_id": "nope", "why": "test"}  # noqa: E731
    out = table.run(Script(bad), {"A": Scripted([5.00])}, REQUEST)
    assert out["trace"][-1]["source"] == "fallback" and out["outcome"] == "walked_away"


def test_a_counter_above_the_cap_is_never_sent():
    out = table.run(Script(send("A", 4.81)), {"A": Scripted([5.00])}, REQUEST)
    assert out["trace"][-1]["source"] == "fallback"
    assert all(m.get("type") != "send" for m in out["threads"]["A"])


def test_deadline_hands_over_to_the_closing_move():
    ticks = iter([0, 0] + [100] * 10)  # start, first decision, then past the limit
    sup = {"A": Scripted([5.00, 4.50])}
    out = table.run(Script(send("A", 4.00), send("A", 4.10)), sup, REQUEST, time_limit_s=60, clock=lambda: next(ticks))
    assert [e["source"] for e in out["trace"]] == ["buyer", "deadline"]
    assert out["outcome"] == "accepted" and out["terms"]["unit_price"] == 4.50


def test_round_limit_stops_a_buyer_that_never_closes():
    forever = lambda threads: {"supplier_id": "A", "type": "send", "terms": terms(4.00), "body": "", "why": "loop"}  # noqa: E731

    class Loop:
        def decide(self, threads):
            return forever(threads)

    out = table.run(Loop(), {"A": Scripted([5.00, 4.90, 4.70])}, REQUEST, round_limit=3)
    sends = [m for m in out["threads"]["A"] if m.get("type") == "send"]
    assert len(sends) == 3 - 1  # the RFQ counts as the first buyer message
    assert out["trace"][-1]["source"] == "fallback" and out["outcome"] == "accepted"


def test_ended_threads_get_no_more_messages_and_all_ended_means_walk():
    sup = {"A": Scripted([5.00], status="walked_away")}
    out = table.run(Script(send("A", 4.00)), sup, REQUEST)
    assert out["outcome"] == "walked_away"
    assert [m["type"] for m in sup["A"].seen] == ["rfq"]  # nothing is sent to a supplier that walked
    assert [e["source"] for e in out["trace"]] == ["table"]
