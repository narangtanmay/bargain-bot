import random

from negotiator import signing
from negotiator.buyer import accept_gate
from negotiator.checks import effective_cap, must_have_result, run_checks, terms_checks
from negotiator.engine import negotiate
from negotiator.suppliers import PERSONAS, Supplier

REQUEST = {"item": "bracket", "quantity": 100, "max_unit_price_eur": 4.80, "delivery_days": 21, "must_haves": []}


def terms(price=4.50, **extra):
    return {"unit_price": price, "quantity": 100, "delivery_days": 14, "payment_terms_days": 30,
            "terms": ["ISO 9001 certified"], **extra}


def names(checks, passed=False):
    return [name for name, ok, _ in checks if ok == passed]


def signed_deal(price=4.50):
    """A real supplier's signed confirmation of its standing sheet, and the inputs the engine gives the checker."""
    s = Supplier(PERSONAS[0], REQUEST, random.Random(1), "normal", 1)
    s.respond({"type": "rfq"})
    s.price = price
    sheet = s.respond({"type": "send", "terms": {"unit_price": price}})["term_sheets"][0]
    conf = s.respond({"type": "accept", "term_sheet_id": sheet["term_sheet_id"]})["confirmation"]
    quote = {"supplier": conf["supplier"], "unit_price_eur": conf["unit_price"], "quantity": conf["quantity"],
             "total_eur": conf["total"], "delivery_days": conf["delivery_days"],
             "payment_terms_days": conf["payment_terms_days"], "terms": conf["terms"], "confirmation": conf}
    return quote, s.public_key, sheet


def failed(quote, key, sheet, request=REQUEST, opening=5.00):
    return [c["name"] for c in run_checks(request, quote, opening=opening, public_key=key, accepted=sheet) if not c["passed"]]


def test_a_signed_matching_confirmation_passes_every_check():
    quote, key, sheet = signed_deal()
    assert failed(quote, key, sheet) == []


def test_price_must_be_strictly_below_the_opening_quote():
    assert "price_below_opening_quote" in names(terms_checks(REQUEST, terms(4.50), 4.50))
    assert "price_below_opening_quote" not in names(terms_checks(REQUEST, terms(4.49), 4.50))


def test_cap_is_inclusive():
    assert "unit_price_within_cap" not in names(terms_checks(REQUEST, terms(4.80), 5.00))
    assert "unit_price_within_cap" in names(terms_checks(REQUEST, terms(4.81), 5.00))


def test_max_total_caps_the_total_and_tightens_the_unit_cap():
    request = {**REQUEST, "max_total_eur": 450.0}
    assert effective_cap(request) == 4.50 and effective_cap(REQUEST) == 4.80
    assert "total_within_max" in names(terms_checks(request, terms(4.51), 5.00))
    assert "total_within_max" not in names(terms_checks(request, terms(4.50), 5.00))


def test_buyer_gate_and_checker_agree_on_every_terms_check():
    for price, opening in ((4.50, 5.00), (4.80, 5.00), (4.81, 5.00), (4.60, 4.60), (4.59, 4.60)):
        for extra in ({}, {"delivery_days": 30}, {"quantity": 99}):
            t = terms(price, **extra)
            assert accept_gate(REQUEST, t, opening)[0] == (names(terms_checks(REQUEST, t, opening)) == [])


def test_structured_must_haves_compare_fields_exactly():
    req = REQUEST
    assert must_have_result("payment_terms_days >= 30", terms(), req)[0]
    assert not must_have_result("payment_terms_days >= 45", terms(), req)[0]
    assert must_have_result("delivery_days <= 14", terms(), req)[0]
    assert not must_have_result("delivery_days < 14", terms(), req)[0]
    assert not must_have_result("food_safe == true", terms(), req)[0]  # a field the quote does not have
    assert must_have_result("food_safe == true", terms(food_safe=True), req)[0]
    assert must_have_result("payment terms net 30", terms(), req)[0]  # free text still works


def test_tampered_or_unsigned_confirmation_fails_the_signature_check():
    quote, key, sheet = signed_deal()
    tampered = {**quote, "confirmation": {**quote["confirmation"], "terms": []}}
    assert "confirmation_signature_valid" in failed(tampered, key, sheet)
    unsigned = {**quote, "confirmation": {k: v for k, v in quote["confirmation"].items() if k != "signature"}}
    assert "confirmation_signature_valid" in failed(unsigned, key, sheet)
    other = signing.public_hex(signing.key_from_seed(1, "B"))
    assert "confirmation_signature_valid" in failed(quote, other, sheet)


def test_confirmation_must_match_the_accepted_sheet():
    quote, key, sheet = signed_deal()
    other_sheet = {**sheet, "terms": {**sheet["terms"], "unit_price": 4.40}}
    assert failed(quote, key, other_sheet) == ["confirmation_matches_accepted_sheet"]
    assert "confirmation_matches_accepted_sheet" in failed(quote, key, {**sheet, "term_sheet_id": "A-99"})


def test_max_total_request_line_reaches_the_buyer_and_the_checker():
    text = open("examples/request.txt").read()
    tight = negotiate(text + "max_total_eur: 8400\n", seed=1)
    assert tight["status"] == "deal" and tight["quote"]["total_eur"] <= 8400
    assert negotiate(text + "max_total_eur: 1000\n", seed=1)["status"] == "no_deal"
    assert negotiate(text + "max_total_eur: lots\n", seed=1)["status"] == "invalid_request"


def test_structured_must_have_line_steers_the_award():
    text = open("examples/request.txt").read()
    result = negotiate(text + "must_have: payment_terms_days >= 45\n", seed=1)
    assert result["status"] == "deal" and result["quote"]["supplier"] == "Supplier B"  # only B gives net 45
