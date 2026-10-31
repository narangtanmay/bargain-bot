"""The negotiation table: RFQ to every supplier, then one buyer decision at a time until accept or walk away.

Loop adapted from the upstream buyer-agent runner (`arena_kit/play.py` `play`, MIT, Copyright (c) 2026 Tacto Technology
GmbH), with in-process suppliers instead of the arena's HTTP API. The table, not the buyer, guarantees the
rules that are never cut: every accept and every counter passes the caps, and every accept is a standing
sheet that passes the accept gate. A failed or invalid buyer move becomes the closing move, never a model call.
Buyer and suppliers only ever get JSON copies, so neither can read or change the other's objects.
"""

import hashlib
import json
import time

from . import protocol as pr
from .buyer import accept_gate, closing_move, opening_price
from .checks import effective_cap

# The RFQ tells suppliers what is wanted, never the caller's cap.
RFQ_FIELDS = ("item", "quantity", "delivery_days", "must_haves")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _copy(obj):
    return json.loads(canonical(obj))


def _respond(supplier, message):
    try:
        return supplier.respond(_copy(message))
    except Exception as e:  # a broken supplier counts as no bid; it must not end the negotiation
        return {"error": repr(e)}


def check_move(request, threads, move, round_limit):
    """None if the table may carry out this buyer move, else the reason it may not."""
    if not isinstance(move, dict) or move.get("type") not in pr.DECISIONS:
        return "unknown move"
    if move["type"] == "walk_away":
        return None
    sid = move.get("supplier_id")
    if sid not in pr.live_threads(threads):
        return f"supplier {sid!r} is not in a live thread"
    events = threads[sid]
    if move["type"] == "accept":
        sheet_id, terms = pr.standing(events)
        if not sheet_id or move.get("term_sheet_id") != sheet_id:
            return f"{move.get('term_sheet_id')!r} is not {sid}'s standing sheet"
        ok, reasons = accept_gate(request, terms, opening_price(events))
        return None if ok else "accept gate: " + "; ".join(reasons)
    if pr.moves_left(events, round_limit) <= 0:
        return f"no messages left to {sid}"
    if pr.latest(events).get("status") == "final_offer":
        return f"{sid} made a final offer; countering it ends the thread"
    errors = pr.validate_terms(move.get("terms"))
    if errors:
        return "; ".join(errors)
    terms = move["terms"]
    if terms["unit_price"] > effective_cap(request):
        return f"counter {terms['unit_price']:.2f} above the cap {effective_cap(request):.2f}"
    if terms["quantity"] != request["quantity"] or terms["delivery_days"] > request["delivery_days"]:
        return "counter changes the quantity or the delivery deadline"
    return None


def run(buyer, suppliers, request, round_limit=pr.ROUND_LIMIT, time_limit_s=60, clock=time.monotonic):
    """Play one negotiation. `suppliers`: {supplier_id: object with respond(message) -> reply}.
    Returns {outcome, supplier_id, term_sheet_id, terms, confirmation, threads, order, trace, log_hash, seconds}.
    Wall time stays out of the trace, so the same replies always give the same trace and `log_hash`."""
    start, wall = clock(), time.perf_counter()
    rfq = {"from": "buyer", "type": "rfq", **{k: request.get(k) for k in RFQ_FIELDS}}
    threads, order, trace = {sid: [] for sid in suppliers}, [], []

    def put(sid, msg):  # every message in the order it happened, across threads: [supplier_id, index]
        order.append([sid, len(threads[sid])])
        threads[sid].append(msg)

    def message(sid, msg):
        put(sid, msg)
        return _respond(suppliers[sid], msg)

    for sid in suppliers:
        put(sid, pr.clean_supplier_message(sid, message(sid, dict(rfq))))

    def close_all(keep=None):
        for sid in pr.live_threads(threads):
            if sid != keep:
                message(sid, {"from": "buyer", "type": "close"})

    def finish(outcome, sid=None, sheet_id=None, terms=None, confirmation=None):
        log = {"threads": threads, "trace": trace}
        return {"outcome": outcome, "supplier_id": sid, "term_sheet_id": sheet_id, "terms": terms,
                "confirmation": confirmation, "threads": threads, "order": order, "trace": trace,
                "log_hash": hashlib.sha256(canonical(log)).hexdigest(), "seconds": round(time.perf_counter() - wall, 3)}

    for _ in range(round_limit * max(1, len(suppliers)) + 1):
        if not pr.live_threads(threads):
            move, source = {"supplier_id": None, "type": "walk_away", "why": "every supplier has ended its thread"}, "table"
        elif clock() - start >= time_limit_s:
            move, source = closing_move(request, threads), "deadline"
        else:
            try:
                move, source = buyer.decide(_copy(threads)), "buyer"
                problem = check_move(request, threads, move, round_limit)
            except Exception as e:
                problem = f"buyer failed: {e!r}"
            if problem:
                move, source = closing_move(request, threads), "fallback"
                move["why"] = f"{problem}; {move['why']}"
        kind, sid = move["type"], move.get("supplier_id")
        price = (move.get("terms") or {}).get("unit_price") if kind == "send" else None
        if kind == "accept":
            price = pr.standing(threads[sid])[1]["unit_price"]
        trace.append({"n": len(trace) + 1, "supplier_id": sid, "action": kind, "unit_price": price,
                      "term_sheet_id": move.get("term_sheet_id"), "source": source, "why": move.get("why")})
        if kind == "walk_away":
            close_all()
            return finish("walked_away")
        if kind == "accept":
            sheet_id, terms = pr.standing(threads[sid])
            reply = pr.clean_supplier_message(sid, message(sid, {"from": "buyer", "type": "accept", "term_sheet_id": sheet_id}))
            put(sid, reply)
            close_all(keep=sid)
            return finish("accepted", sid, sheet_id, terms, reply.get("confirmation"))
        reply = message(sid, {"from": "buyer", "type": "send", "terms": move["terms"], "body": move.get("body", "")})
        put(sid, pr.clean_supplier_message(sid, reply))

    trace.append({"n": len(trace) + 1, "supplier_id": None, "action": "walk_away", "unit_price": None,
                  "term_sheet_id": None, "source": "table", "why": "decision limit reached"})
    close_all()
    return finish("walked_away")
