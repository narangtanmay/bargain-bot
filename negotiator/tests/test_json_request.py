"""Regression: JSON Task descriptions must reach the existing checker as structured requests."""
import json

import pytest

from negotiator.engine import negotiate
from negotiator.request import parse_request

REQUEST = {"item": "stainless steel mounting bracket", "quantity": 2000,
           "max_unit_price_eur": 4.8, "delivery_days": 21,
           "must_haves": ["delivery within deadline", "payment terms net 30"]}
TEXT = "item: stainless steel mounting bracket\nquantity: 2000\nmax_unit_price_eur: 4.8\ndelivery_days: 21\nmust_have: delivery within deadline\nmust_have: payment terms net 30\n"


def test_json_and_text_have_identical_negotiation_and_verification_results():
    assert negotiate(json.dumps(REQUEST), seed=1) == negotiate(TEXT, seed=1)


def test_procurement_json_aliases_preserve_caps_terms_and_absolute_deadline():
    payload = {"product": REQUEST["item"], "quantity": 2000,
               "maximum_unit_price": {"amount": "4.80", "currency": "EUR"},
               "maximum_total_price": {"amount": "9600.00", "currency": "EUR"},
               "request_date": "2026-10-31", "delivery_deadline": "2026-11-21",
               "mandatory_commercial_terms": REQUEST["must_haves"]}
    request, errors = parse_request(json.dumps(payload))
    assert not errors
    assert request == {**REQUEST, "max_total_eur": 9600.0}
    assert negotiate(json.dumps(payload))["status"] == "deal"


@pytest.mark.parametrize("patch", [
    {"quantity": True}, {"quantity": 1.5}, {"item": "bracket\nmax_unit_price_eur: 999"},
    {"must_haves": "net 30"}, {"max_unit_price_eur": "NaN"},
    {"supplier_quotes": "bad"}, {"supplier_quotes": [{"name": "A", "unit_price_eur": True}]},
])
def test_invalid_json_fields_fail_closed(patch):
    result = negotiate(json.dumps({**REQUEST, **patch}))
    assert result["status"] == "invalid_request"
    assert result["quote"] is None


@pytest.mark.parametrize("text", ['{bad json', '[]', '{"product": "bracket"}',
    '{"maximum_unit_price": {"amount": 5, "currency": "USD"}}'])
def test_malformed_or_incomplete_json_is_not_a_deal(text):
    assert negotiate(text)["status"] == "invalid_request"


def test_expired_absolute_deadline_is_rejected():
    payload = {k: v for k, v in REQUEST.items() if k != "delivery_days"}
    payload.update(request_date="2026-10-31", delivery_deadline="2026-10-31")
    result = negotiate(json.dumps(payload))
    assert result["status"] == "invalid_request"
    assert "must be after" in result["errors"][0]


def test_json_supplied_quotes_keep_their_source_label():
    payload = {**REQUEST, "supplier_quotes": [
        {"name": name, "unit_price_eur": price} for name, price in [("Shop A", 5.0), ("Shop B", 5.2), ("Shop C", 5.1)]]}
    result = negotiate(json.dumps(payload))
    assert result["status"] == "deal"
    assert result["opening_prices_source"] == "provided"
    assert "did not sign or confirm anything" in result["summary_markdown"]
