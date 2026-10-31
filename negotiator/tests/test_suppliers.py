import json
import random
from pathlib import Path

from negotiator import signing
from negotiator.engine import negotiate
from negotiator.suppliers import BROKEN_TOTAL_DELTA_EUR, PERSONAS, Supplier

ROOT = Path(__file__).resolve().parent.parent
TEXT = (ROOT / "examples" / "request.txt").read_text()
REQUEST = {"item": "bracket", "quantity": 100, "max_unit_price_eur": 4.80, "delivery_days": 21, "must_haves": []}


def supplier(persona=PERSONAS[0], scenario="normal", seed=1):
    return Supplier(persona, REQUEST, random.Random(seed), scenario, seed)


def send(s, price):
    return s.respond({"type": "send", "terms": {"unit_price": price}})


def test_deal_confirmation_verifies_with_the_published_public_key():
    result = negotiate(TEXT, seed=1)
    conf = result["quote"]["confirmation"]
    assert result["status"] == "deal"
    assert signing.verify(result["public_keys"][conf["supplier"]], conf)
    assert conf["term_sheet_id"] and conf["unit_price"] == result["quote"]["unit_price_eur"]


def test_tampered_confirmation_or_wrong_key_fails_verification():
    result = negotiate(TEXT, seed=1)
    conf, keys = result["quote"]["confirmation"], result["public_keys"]
    assert not signing.verify(keys[conf["supplier"]], {**conf, "unit_price": 0.01})
    assert not signing.verify(keys[conf["supplier"]], {**conf, "total": conf["total"] - 1})
    other = next(k for name, k in keys.items() if name != conf["supplier"])
    assert not signing.verify(other, conf)
    assert not signing.verify(keys[conf["supplier"]], {k: v for k, v in conf.items() if k != "signature"})


def test_keys_are_per_supplier_and_reproducible_per_seed():
    a, b = negotiate(TEXT, seed=1)["public_keys"], negotiate(TEXT, seed=1)["public_keys"]
    assert a == b and len(set(a.values())) == 3
    assert negotiate(TEXT, seed=2)["public_keys"] != a


def test_concession_schedule_never_rises_never_breaks_the_floor_and_ends_final():
    s = supplier(PERSONAS[1])  # Supplier B: final offer from round 4
    s.respond({"type": "rfq"})
    prices, statuses = [s.price], []
    for _ in range(PERSONAS[1].final_round):
        reply = send(s, 0.01)
        prices.append(s.price)
        statuses.append(reply["status"])
    assert prices == sorted(prices, reverse=True) and min(prices) >= s._floor
    assert statuses[-1] == "final_offer" and set(statuses[:-1]) == {"open"}
    assert send(s, 0.01)["status"] == "walked_away"  # pushed after its final offer


def test_supplier_agrees_when_the_buyer_reaches_its_next_price():
    s = supplier()
    s.respond({"type": "rfq"})
    reply = send(s, s.next_price() + 0.0)
    assert reply["status"] == "agreed"


def test_accepting_a_stale_sheet_gets_no_confirmation():
    s = supplier()
    first = s.respond({"type": "rfq"})["term_sheets"][0]["term_sheet_id"]
    send(s, 0.01)
    reply = s.respond({"type": "accept", "term_sheet_id": first})
    assert "confirmation" not in reply


def test_broken_quote_is_validly_signed_but_its_total_is_wrong():
    s = supplier(scenario="broken_quote")
    sheet = s.respond({"type": "rfq"})["term_sheets"][0]["term_sheet_id"]
    conf = s.respond({"type": "accept", "term_sheet_id": sheet})["confirmation"]
    assert signing.verify(s.public_key, conf)
    assert conf["total"] == round(s.price * REQUEST["quantity"] + BROKEN_TOTAL_DELTA_EUR, 2)
    result = negotiate(TEXT, seed=1, scenario="broken_quote")
    assert result["status"] == "no_deal" and result["quote"] is None


def test_no_supplier_internals_or_scenario_reach_the_result():
    for scenario in ("normal", "above_cap", "broken_quote"):
        result = negotiate(TEXT, seed=3, scenario=scenario)
        result.pop("summary_markdown")  # its disclaimer says the floors exist, without any value
        dumped = json.dumps(result)
        for secret in ("floor", "markup", "scenario", "above_cap", "broken_quote", "private"):
            assert secret not in dumped, (scenario, secret)


def test_buyer_and_table_never_mention_the_scenario():
    for module in ("buyer.py", "table.py", "protocol.py"):
        assert "scenario" not in (ROOT / "negotiator" / module).read_text()
