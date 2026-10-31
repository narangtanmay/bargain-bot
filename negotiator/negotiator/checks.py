"""Deterministic checks on a quote against the buyer's request. Pure code, no LLM.

`terms_checks` judges one term sheet; the buyer's accept gate runs exactly these, so the buyer never accepts a
sheet that this checker would reject on its terms. `run_checks` adds what only exists after an accept: the
supplier's signed confirmation, its match with the accepted sheet, and its total.
"""

import math
import operator
import re

from . import signing

STOPWORDS = {"with", "must", "have", "within", "from", "terms", "the", "and", "for"}
# Structured must-have rules, `field op value` (adapted from the upstream `cost.must_haves_ok`; see LICENSE-NOTICE.md)
OPS = {"<=": operator.le, ">=": operator.ge, "==": operator.eq, "!=": operator.ne, "<": operator.lt, ">": operator.gt}
RULE = re.compile(r"^\s*([a-z_][a-z0-9_]*)\s*(<=|>=|==|!=|<|>)\s*(\S.*?)\s*$", re.I)
MATCHED_FIELDS = ("term_sheet_id", "unit_price", "quantity", "delivery_days", "payment_terms_days", "terms")


def effective_cap(request):
    """The highest unit price the caller allows: the unit cap, and the total cap spread over the quantity."""
    cap = request["max_unit_price_eur"]
    if request.get("max_total_eur"):
        cap = min(cap, math.floor(request["max_total_eur"] / request["quantity"] * 100 + 1e-9) / 100)
    return cap


def _rule_value(text):
    low = text.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return float(text)
    except ValueError:
        return text.strip().strip("'\"")


def must_have_result(must_have, terms, request):
    """Return (passed, detail) for one must-have, on protocol terms {unit_price, quantity, delivery_days,
    payment_terms_days, terms}.

    Structured `field op value` rules (e.g. `payment_terms_days >= 30`) compare that field exactly. Free text
    stays supported: payment terms ("net 30") compare payment days; delivery or deadline phrases compare delivery
    days; anything else must have all its words in the quote's terms.
    """
    rule = RULE.match(must_have)
    if rule:
        name, op, raw = rule.group(1).lower(), rule.group(2), rule.group(3)
        if name not in terms:
            return False, f"'{must_have}': the quote has no field {name}"
        have, need = terms[name], _rule_value(raw)
        try:
            ok = OPS[op](have, need)
        except TypeError:
            ok = False
        return bool(ok), f"'{must_have}': {name} is {have!r}"
    text = must_have.lower()
    number = re.search(r"\d+", text)
    if "payment" in text or re.search(r"\bnet\b", text):
        if not number:
            return False, f"'{must_have}': no day count to compare"
        need = int(number.group())
        have = terms.get("payment_terms_days") or 0
        return have >= need, f"'{must_have}': net {have} vs required net {need}"
    if "deliver" in text or "deadline" in text or "lead time" in text:
        need = int(number.group()) if number else request["delivery_days"]
        have = terms["delivery_days"]
        return have <= need, f"'{must_have}': {have} days vs at most {need}"
    words = [w for w in re.findall(r"[a-z0-9]+", text) if len(w) >= 3 and w not in STOPWORDS]
    found = " ".join(terms.get("terms", [])).lower()
    missing = [w for w in words if w not in found]
    if not words:
        return False, f"'{must_have}': nothing checkable"
    if missing:
        return False, f"'{must_have}': not in quote terms (missing {', '.join(missing)})"
    return True, f"'{must_have}': found in quote terms"


def must_haves_met(terms, request):
    results = [must_have_result(m, terms, request) for m in request["must_haves"]]
    if not results:
        return True, "no must-haves given"
    return all(ok for ok, _ in results), "; ".join(detail for _, detail in results)


def terms_checks(request, terms, opening):
    """Checks on one term sheet (protocol terms) given the supplier's opening unit price. The cap is inclusive;
    the saving is strict: a deal must be below the supplier's own opening quote."""
    cap, qty, days = request["max_unit_price_eur"], request["quantity"], request["delivery_days"]
    price = terms["unit_price"]
    total = round(price * terms["quantity"], 2)
    max_total = request.get("max_total_eur")
    must_ok, must_detail = must_haves_met(terms, request)
    return [
        ("unit_price_within_cap", price <= cap, f"{price:.2f} {'<=' if price <= cap else '>'} {cap:.2f}"),
        ("total_within_max", max_total is None or total <= max_total,
         "no max_total_eur given" if max_total is None else f"{total:.2f} vs at most {max_total:.2f}"),
        ("price_below_opening_quote", opening is not None and price < opening,
         f"{price:.2f} vs opening quote {opening:.2f}" if opening is not None else "no opening quote"),
        ("quantity_matches", terms["quantity"] == qty, f"{terms['quantity']} vs requested {qty}"),
        ("delivery_within_deadline", terms["delivery_days"] <= days, f"{terms['delivery_days']} days vs at most {days}"),
        ("must_haves_met", must_ok, must_detail),
    ]


def _terms_of(quote):
    return {"unit_price": quote["unit_price_eur"], "quantity": quote["quantity"], "delivery_days": quote["delivery_days"],
            "payment_terms_days": quote["payment_terms_days"], "terms": list(quote.get("terms", []))}


def run_checks(request, quote, opening=None, public_key=None, accepted=None, channel="protocol"):
    """quote is an offer dict, with 'confirmation' set only when the supplier confirmed. `opening` is that
    supplier's opening unit price, `public_key` its signing key, `accepted` the sheet the buyer accepted
    ({term_sheet_id, terms}), all as the buyer side saw them. A `free_text` supplier cannot sign: its signature
    check passes as not applicable, and says that its identity is not verified."""
    terms = _terms_of(quote)
    price, total = quote["unit_price_eur"], quote["total_eur"]
    expected_total = round(price * quote["quantity"], 2)
    conf = quote.get("confirmation")
    has_conf = bool(conf and conf.get("text") and conf.get("quote_id") and conf.get("supplier") == quote["supplier"])
    signed = bool(has_conf and public_key and signing.verify(public_key, conf))
    if channel == "free_text":
        signed = has_conf
        sig_detail = ("not applicable: free-text supplier, identity not verified" if has_conf
                      else "no confirmation to verify")
    elif not has_conf:
        sig_detail = "no confirmation to verify"
    elif not public_key:
        sig_detail = "no public key for this supplier"
    else:
        sig_detail = "Ed25519 signature verifies" if signed else "signature does not verify"
    mismatched = []
    if has_conf and accepted:
        sheet = {"term_sheet_id": accepted["term_sheet_id"], **accepted["terms"]}
        mismatched = [f for f in MATCHED_FIELDS if conf.get(f) != sheet.get(f)]
        if conf.get("total") != round(sheet["unit_price"] * sheet["quantity"], 2):
            mismatched.append("total")
    matches = bool(has_conf and accepted and not mismatched)
    if not has_conf:
        match_detail = "no confirmation to compare"
    elif not accepted:
        match_detail = "no accepted sheet to compare"
    else:
        match_detail = f"matches sheet {accepted['term_sheet_id']}" if matches else f"differs in {', '.join(mismatched)}"
    checks = terms_checks(request, terms, opening) + [
        ("supplier_confirmation_present", has_conf,
         f"quote_id {conf['quote_id']} from {conf['supplier']}" if has_conf else "no confirmation from the supplier"),
        ("confirmation_signature_valid", signed, sig_detail),
        ("confirmation_matches_accepted_sheet", matches, match_detail),
        ("total_consistent", abs(total - expected_total) < 0.005,
         f"{price:.2f} x {quote['quantity']} = {expected_total:.2f}, quote says {total:.2f}"),
    ]
    return [{"name": n, "passed": bool(ok), "detail": d} for n, ok, d in checks]
