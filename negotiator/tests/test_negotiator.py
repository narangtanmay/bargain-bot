import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REQUEST = ROOT / "examples" / "request.txt"
CHECK_NAMES = [
    "unit_price_within_cap",
    "total_within_max",
    "price_below_opening_quote",
    "quantity_matches",
    "delivery_within_deadline",
    "must_haves_met",
    "supplier_confirmation_present",
    "confirmation_signature_valid",
    "confirmation_matches_accepted_sheet",
    "total_consistent",
]


def run_cli(tmp_path, request_file=REQUEST, *extra):
    out = tmp_path / "result.json"
    proc = subprocess.run(
        [sys.executable, "-m", "negotiator", "--request-file", str(request_file), "--out", str(out), *extra],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(out.read_text()), out.read_bytes()


def failed(result):
    return [c["name"] for c in result["checks"] if not c["passed"]]


def test_normal_run_closes_deal_under_cap_with_all_checks_passing(tmp_path):
    result, _ = run_cli(tmp_path, REQUEST, "--seed", "1")

    assert result["status"] == "deal"
    assert result["request"] == {
        "item": "stainless steel mounting bracket",
        "quantity": 2000,
        "max_unit_price_eur": 4.8,
        "delivery_days": 21,
        "must_haves": ["delivery within deadline", "payment terms net 30"],
    }
    quote = result["quote"]
    assert {k: quote[k] for k in ("supplier", "unit_price_eur", "quantity", "total_eur", "delivery_days", "payment_terms_days")} == {
        "supplier": "Supplier A",
        "unit_price_eur": 4.31,
        "quantity": 2000,
        "total_eur": 8620.0,
        "delivery_days": 18,
        "payment_terms_days": 30,
    }
    assert quote["confirmation"]["supplier"] == "Supplier A"
    assert quote["confirmation"]["quote_id"] == "Q-A-cff1806cc2"
    assert "Q-A-cff1806cc2" in quote["confirmation"]["text"]
    assert result["opening_best_unit_price_eur"] == 4.88
    assert result["winner_opening_unit_price_eur"] == 4.88
    assert result["savings_eur"] == 1140.0  # versus the winner's own opening quote
    assert [c["name"] for c in result["checks"]] == CHECK_NAMES
    assert failed(result) == []
    assert "**Outcome:** deal with Supplier A at EUR 4.31 per unit" in result["summary_markdown"]
    assert "simulated demo agents" in result["summary_markdown"]


def test_buyer_cites_rival_offers_and_never_claims_agreement(tmp_path):
    result, _ = run_cli(tmp_path)
    buyer_text = [m["text"] for m in result["transcript"] if m["from"] == "buyer"]

    assert "Thank you for your offer. We can offer EUR 4.07 per unit for 2000 units. Another supplier has offered EUR 4.73 per unit." in buyer_text
    assert not any("agreed" in t for t in buyer_text)


def test_suppliers_use_different_wording(tmp_path):
    result, _ = run_cli(tmp_path)
    openings = {m["supplier"]: m["text"] for m in result["transcript"] if m["from"] == "supplier" and m["round"] == 1}

    assert openings["Supplier A"].startswith("Thank you for the enquiry.")
    assert openings["Supplier B"].startswith("Hello, happy to help.")
    assert openings["Supplier C"].startswith("Quote for stainless steel mounting bracket")


def test_above_cap_gives_no_deal_and_null_quote(tmp_path):
    result, _ = run_cli(tmp_path, REQUEST, "--seed", "1", "--scenario", "above_cap")

    assert result["status"] == "no_deal"
    assert result["quote"] is None
    assert result["savings_eur"] == 0.0
    assert failed(result) == ["unit_price_within_cap", "supplier_confirmation_present", "confirmation_signature_valid",
                              "confirmation_matches_accepted_sheet"]
    assert result["checks"][0]["detail"] == "5.23 > 4.80"
    assert not any(m["text"].startswith("We accept") for m in result["transcript"])


def test_broken_quote_fails_total_consistent_and_gives_no_deal(tmp_path):
    result, _ = run_cli(tmp_path, REQUEST, "--seed", "1", "--scenario", "broken_quote")

    assert result["status"] == "no_deal"
    assert result["quote"] is None
    assert failed(result) == ["confirmation_matches_accepted_sheet", "total_consistent"]
    assert result["checks"][-1]["detail"] == "4.31 x 2000 = 8620.00, quote says 8720.00"
    assert "[FAIL] total_consistent" in result["summary_markdown"]


def test_invalid_request_reports_each_problem(tmp_path):
    bad = tmp_path / "bad.txt"
    bad.write_text("item: bracket\nquantity: lots\nmax_unit_price_eur: -1\n")
    result, _ = run_cli(tmp_path, bad)

    assert result["status"] == "invalid_request"
    assert result["quote"] is None
    assert result["checks"] == []
    assert result["errors"] == [
        "missing delivery_days",
        "quantity must be a positive whole number, got 'lots'",
        "max_unit_price_eur must be a positive number, got '-1'",
    ]


def test_keys_are_case_insensitive_and_unknown_lines_ignored(tmp_path):
    req = tmp_path / "req.txt"
    req.write_text("Notes: hello\nDELIVERY_DAYS: 21\nItem: bracket\nQuantity: 500\nMax_Unit_Price_EUR: 4.80\n")
    result, _ = run_cli(tmp_path, req)

    assert result["status"] == "deal"
    assert result["request"]["quantity"] == 500
    assert result["quote"]["quantity"] == 500


def test_unmet_keyword_must_have_blocks_the_deal(tmp_path):
    req = tmp_path / "req.txt"
    req.write_text(REQUEST.read_text() + "must_have: RoHS declaration\n")
    result, _ = run_cli(tmp_path, req)

    assert result["status"] == "no_deal"
    assert "must_haves_met" in failed(result)


def test_same_seed_gives_identical_json_and_different_seed_differs(tmp_path):
    _, first = run_cli(tmp_path, REQUEST, "--seed", "7")
    _, second = run_cli(tmp_path, REQUEST, "--seed", "7")
    _, other = run_cli(tmp_path, REQUEST, "--seed", "8")

    assert first == second
    assert first != other


def test_many_seeds_never_accept_above_cap_late_delivery_or_without_saving(tmp_path):
    from negotiator.engine import negotiate

    text = REQUEST.read_text()
    for seed in range(200):
        for scenario in ("normal", "above_cap"):
            result = negotiate(text, seed=seed, scenario=scenario)
            if result["status"] == "deal":
                assert result["quote"]["unit_price_eur"] <= 4.8
                assert result["quote"]["delivery_days"] <= 21
                assert result["quote"]["unit_price_eur"] < result["winner_opening_unit_price_eur"]  # always a saving
                assert result["savings_eur"] > 0
            else:
                assert result["quote"] is None
            assert scenario == "normal" or result["status"] == "no_deal"


QUOTES = ["Print Shop Nord = 14.90", "Merch Hub = 13.50", "Stitch & Co = 16.00"]
NOTE = "Opening prices are real quotes supplied by the buyer; the negotiation rounds, delivery and payment terms are simulated."


def quote_request(tmp_path, quotes, *extra):
    req = tmp_path / "quotes.txt"
    req.write_text(REQUEST.read_text() + "".join(f"supplier_quote: {q}\n" for q in quotes))
    return run_cli(tmp_path, req, *extra)[0]


def test_three_quotes_become_the_opening_offers(tmp_path):
    result = quote_request(tmp_path, ["Print Shop Nord = 4.90", "Merch Hub = 4.50", "Stitch & Co = 5.00"])
    openings = [m for m in result["transcript"] if m["round"] == 1 and m["from"] == "supplier"]
    assert [(m["supplier"], m["unit_price_eur"]) for m in openings] == [("Print Shop Nord", 4.9), ("Merch Hub", 4.5), ("Stitch & Co", 5.0)]
    assert result["opening_prices_source"] == "provided"
    md = result["summary_markdown"]
    assert md.split("\n")[2] == NOTE
    assert "**Outcome (simulated negotiation):** simulated deal with" in md
    assert "simulated confirmation" in md
    assert "at a simulated final price" in md
    assert "Simulated agreed terms" in md


def test_two_quotes_is_invalid_request(tmp_path):
    assert quote_request(tmp_path, QUOTES[:2])["status"] == "invalid_request"


def test_malformed_quote_is_invalid_request(tmp_path):
    for bad in ("Print Shop Nord = abc", "Print Shop Nord = -1", "Print Shop Nord 14.90", " = 14.90"):
        assert quote_request(tmp_path, [bad, *QUOTES[1:]])["status"] == "invalid_request", bad


def test_above_cap_with_provided_quotes_is_invalid_request(tmp_path):
    assert quote_request(tmp_path, QUOTES, "--scenario", "above_cap")["status"] == "invalid_request"


def test_confirmation_uses_provided_name_and_stable_quote_id(tmp_path):
    result = quote_request(tmp_path, ["Print Shop Nord = 4.90", "Merch Hub = 4.50", "Stitch & Co = 5.00"])
    quote = result["quote"]
    assert quote["supplier"] in quote["confirmation"]["text"]
    assert quote["confirmation"]["text"].count("Supplier ") == 0
    assert quote["confirmation"]["quote_id"][:3] in ("Q-A", "Q-B", "Q-C")
    assert "deterministic code; no LLM" in result["summary_markdown"]
    assert "All prices come from deterministic code" not in result["summary_markdown"]


def test_no_quotes_stays_simulated_and_seed_1_stable(tmp_path):
    result, _ = run_cli(tmp_path, REQUEST, "--seed", "1")
    assert result["opening_prices_source"] == "simulated"
    assert NOTE not in result["summary_markdown"]
    assert (result["quote"]["supplier"], result["quote"]["unit_price_eur"]) == ("Supplier A", 4.31)


def test_provided_quote_summary_says_the_named_companies_signed_nothing(tmp_path):
    result = quote_request(tmp_path, ["Print Shop Nord = 4.90", "Merch Hub = 4.50", "Stitch & Co = 5.00"])
    assert "did not sign or confirm anything" in result["summary_markdown"]
    simulated = run_cli(tmp_path, REQUEST, "--seed", "1")[0]
    assert "did not sign or confirm anything" not in simulated["summary_markdown"]


def test_supplier_quote_below_two_cents_does_not_crash(tmp_path):
    # Regression: a quote under EUR 0.02 rounded the derived floor to 0.00 and divided by it (ZeroDivisionError).
    result = quote_request(tmp_path, ["Print Shop Nord = 0.01", "Merch Hub = 0.015", "Stitch & Co = 4.50"])
    assert result["status"] in ("deal", "no_deal")
    if result["status"] == "deal":
        assert result["quote"]["unit_price_eur"] < result["winner_opening_unit_price_eur"]


@pytest.mark.parametrize("reply", [None, "malformed", {"status": "no_bid", "term_sheets": []}, "timeout"])
def test_no_supplier_offer_returns_no_deal_json_from_the_cli(tmp_path, monkeypatch, reply):
    from negotiator.__main__ import main
    from negotiator.suppliers import Supplier

    def unavailable(self, message):
        if reply == "timeout":
            raise TimeoutError("supplier did not reply")
        return reply

    monkeypatch.setattr(Supplier, "respond", unavailable)
    out = tmp_path / "result.json"
    main(["--request-file", str(REQUEST), "--out", str(out)])
    result = json.loads(out.read_text())

    assert result["status"] == "no_deal"
    assert result["quote"] is None
    assert result["opening_best_unit_price_eur"] is None
    assert result["winner_opening_unit_price_eur"] is None
    assert result["savings_eur"] == 0.0
    assert result["checks"] == []
    assert len(result["log_hash"]) == 64
    assert len(result["public_keys"]) == 3
    assert len(result["transcript"]) == 6
    assert not any(m["text"].startswith("We accept") for m in result["transcript"])
    assert "No supplier returned a usable offer" in result["summary_markdown"]
    assert "## Negotiation log" in result["summary_markdown"]
    assert "Best offer considered" not in result["summary_markdown"]


@pytest.mark.parametrize("silent_ids", [{"A"}, {"B", "C"}])
def test_silent_suppliers_do_not_prevent_a_verified_deal_from_other_suppliers(monkeypatch, silent_ids):
    from negotiator.engine import negotiate
    from negotiator.suppliers import PERSONAS, Supplier

    respond = Supplier.respond

    def partially_available(self, message):
        return None if self.persona.sid in silent_ids else respond(self, message)

    monkeypatch.setattr(Supplier, "respond", partially_available)
    result = negotiate(REQUEST.read_text(), seed=1)

    assert result["status"] == "deal"
    assert result["quote"]["supplier"] in {p.name for p in PERSONAS if p.sid not in silent_ids}
    assert result["quote"]["unit_price_eur"] <= result["request"]["max_unit_price_eur"]
    assert result["quote"]["unit_price_eur"] < result["winner_opening_unit_price_eur"]
    assert result["savings_eur"] > 0
    assert [c["name"] for c in result["checks"]] == CHECK_NAMES
    assert all(c["passed"] for c in result["checks"])
