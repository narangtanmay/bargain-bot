"""The message protocol between the buyer and supplier agents.

Shape adapted from the Tacto Negotiation Arena starter kit and upstream buyer agent (`arena_kit/play.py`, MIT,
Copyright (c) 2026 Tacto Technology GmbH): one thread of messages per supplier, a status on every supplier
message, term sheets with IDs, and an accept that names the sheet it takes.

Supplier message: {"from": supplier_id, "status": STATUS, "term_sheets": [{"term_sheet_id", "terms"}], "body",
                   "confirmation" (only in the reply to an accept)}
Buyer message:    {"from": "buyer", "type": "rfq" | "send" | "accept" | "close", "terms" (send),
                   "term_sheet_id" (accept), "body"}
Buyer decision:   {"supplier_id", "type": "send" | "accept" | "walk_away", "terms" | "term_sheet_id", "body", "why"}
"""

import math

STATUSES = ("open", "agreed", "final_offer", "walked_away", "no_bid")
ENDED = {"walked_away", "no_bid"}
DONE = {"agreed", "final_offer"}  # final_offer is final: a supplier pushed past it walks
DECISIONS = ("send", "accept", "walk_away")
SUPPLIER_FIELDS = ("status", "term_sheets", "body", "confirmation")
# Free-text suppliers only (`freetext.py`): what the supplier wrote, what the buyer's message was sent as, and why a
# reply could not be read. Protocol suppliers never set them, so their threads and `log_hash` stay as they were.
AUDIT_FIELDS = ("raw_text", "sent_text", "read_error")
ROUND_LIMIT = 10  # buyer messages per thread, RFQ included (the arena's default `round_limit`)


def _number(value):
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def validate_terms(terms):
    """Errors in one term sheet's terms; [] when it is usable."""
    if not isinstance(terms, dict):
        return ["terms must be an object"]
    errors = []
    if not _number(terms.get("unit_price")) or terms["unit_price"] <= 0:
        errors.append("unit_price must be a positive number")
    for key in ("quantity", "delivery_days"):
        value = terms.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            errors.append(f"{key} must be a positive whole number")
    pay = terms.get("payment_terms_days")
    if pay is not None and (not isinstance(pay, int) or isinstance(pay, bool) or pay < 0):
        errors.append("payment_terms_days must be a whole number of days")
    if not isinstance(terms.get("terms", []), list):
        errors.append("terms must be a list")
    return errors


def clean_supplier_message(supplier_id, raw):
    """What the buyer side may see of a supplier reply: known fields only, sender set by the table.
    A malformed reply counts as no bid, so a broken supplier cannot stall or steer the buyer."""
    if not isinstance(raw, dict) or raw.get("status") not in STATUSES:
        return {"from": supplier_id, "status": "no_bid", "term_sheets": [], "body": "(malformed reply)"}
    sheets = raw.get("term_sheets") or []
    if not isinstance(sheets, list) or any(
        not isinstance(s, dict) or not isinstance(s.get("term_sheet_id"), str) or validate_terms(s.get("terms"))
        for s in sheets
    ):
        return {"from": supplier_id, "status": "no_bid", "term_sheets": [], "body": "(malformed term sheet)"}
    msg = {k: raw[k] for k in SUPPLIER_FIELDS if k in raw}
    msg.update({k: raw[k] for k in AUDIT_FIELDS if isinstance(raw.get(k), str)})
    msg["term_sheets"] = [{"term_sheet_id": s["term_sheet_id"], "terms": s["terms"]} for s in sheets]
    return {"from": supplier_id, **msg}


def latest(events):
    """The supplier's latest message in a thread (`play.latest`)."""
    return next(m for m in reversed(events) if m.get("from") != "buyer")


def standing(events):
    """(term_sheet_id, terms) of the supplier's standing sheet, or (None, {}) (`play.standing`)."""
    sheets = latest(events).get("term_sheets") or []
    return (sheets[0]["term_sheet_id"], sheets[0]["terms"]) if sheets else (None, {})


def opening(events):
    """(term_sheet_id, terms) of the supplier's opening quote, or (None, {})."""
    first = next((m for m in events if m.get("from") != "buyer"), None)
    sheets = (first or {}).get("term_sheets") or []
    return (sheets[0]["term_sheet_id"], sheets[0]["terms"]) if sheets else (None, {})


def sheet_ids(events):
    """Every term sheet ID the supplier has sent in this thread."""
    return {s["term_sheet_id"] for m in events if m.get("from") != "buyer" for s in m.get("term_sheets") or []}


def live_threads(threads):
    """Suppliers whose thread has not ended (`play.live_threads`)."""
    return [sid for sid, events in threads.items() if latest(events).get("status") not in ENDED]


def moves_left(events, round_limit):
    """Buyer messages still allowed in this thread; the RFQ counts (`play.moves_left`)."""
    return round_limit - sum(m.get("from") == "buyer" for m in events)
