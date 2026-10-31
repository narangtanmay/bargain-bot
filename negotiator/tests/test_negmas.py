import json

import pytest

pytest.importorskip("negmas")  # dev-only dependency (requirements-dev.txt); skipped where it is not installed

from negotiator.engine import make_suppliers, negotiate  # noqa: E402
from negotiator.request import parse_request  # noqa: E402

TEXT = open("examples/request.txt").read()


def test_negmas_runs_reproduce_per_seed():
    assert json.dumps(negotiate(TEXT, seed=4, suppliers="negmas")) == json.dumps(negotiate(TEXT, seed=4, suppliers="negmas"))


def test_negmas_deals_keep_every_rule():
    for seed in range(15):
        r = negotiate(TEXT, seed=seed, suppliers="negmas")
        assert r["status"] == "deal" and r["supplier_model"].startswith("negmas: independent strategies")
        q = r["quote"]
        assert q["unit_price_eur"] <= 4.80 and q["unit_price_eur"] < r["winner_opening_unit_price_eur"]
        assert all(c["passed"] for c in r["checks"])
        floor = next(s for s in make_suppliers(parse_request(TEXT)[0], seed, "normal", "negmas").values()
                     if s.name == q["supplier"])._floor
        assert q["unit_price_eur"] >= floor  # a NegMAS seller never agrees below the reservation price we gave it


def test_negmas_scenarios_give_no_deal():
    for scenario in ("above_cap", "broken_quote"):
        for seed in range(5):
            assert negotiate(TEXT, seed=seed, scenario=scenario, suppliers="negmas")["status"] == "no_deal"


def test_negmas_cannot_be_combined_with_real_quotes():
    text = TEXT + "".join(f"supplier_quote: {n} = 5.00\n" for n in ("A", "B", "C"))
    assert negotiate(text, seed=1, suppliers="negmas")["status"] == "invalid_request"


def test_reservation_prices_and_strategy_internals_stay_out_of_the_result():
    r = negotiate(TEXT, seed=2, suppliers="negmas")
    r.pop("summary_markdown")
    dumped = json.dumps(r)
    for secret in ("reserved", "_floor", "utility", "Negotiator"):
        assert secret not in dumped


def test_default_suppliers_are_unchanged_by_the_negmas_option():
    assert "supplier_model" not in negotiate(TEXT, seed=1)
    assert json.dumps(negotiate(TEXT, seed=1)) == json.dumps(negotiate(TEXT, seed=1, suppliers="simulated"))


def test_baseline_buyer_obeys_every_rule_and_is_not_the_default():
    for suppliers in ("simulated", "negmas"):
        for seed in range(10):
            r = negotiate(TEXT, seed=seed, suppliers=suppliers, buyer="baseline")
            if r["status"] == "deal":
                q = r["quote"]
                assert q["unit_price_eur"] <= 4.80 and q["unit_price_eur"] < r["winner_opening_unit_price_eur"]
                assert all(c["passed"] for c in r["checks"])
    assert json.dumps(negotiate(TEXT, seed=1)) == json.dumps(negotiate(TEXT, seed=1, buyer="ported"))
