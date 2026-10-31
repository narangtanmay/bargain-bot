"""Glue: parse the request, run the table (the adapted buyer vs three simulated suppliers), check the result,
and build the result JSON in `CONTRACT.md`."""

import random

from . import protocol as pr
from . import table
from .buyer import Buyer, eligible
from .checks import run_checks
from .freetext import FreeTextAdapter, ProseSupplier
from .request import parse_channel, parse_request
from .summary import summary_markdown
from .tactician import Tactician
from .suppliers import PERSONAS, Supplier

SCENARIOS = ("normal", "above_cap", "broken_quote")
TIME_LIMIT_S = 60  # well inside the worker's 120 s call timeout


def _offer(name, terms, confirmation=None):
    return {"supplier": name, "unit_price_eur": terms["unit_price"], "quantity": terms["quantity"],
            "total_eur": round(terms["unit_price"] * terms["quantity"], 2), "delivery_days": terms["delivery_days"],
            "payment_terms_days": terms.get("payment_terms_days"), "terms": list(terms.get("terms", [])),
            "confirmation": confirmation}


def _from_confirmation(conf):
    """The deal as the supplier signed it: these are the numbers the checker verifies."""
    return {"supplier": conf["supplier"], "unit_price_eur": conf["unit_price"], "quantity": conf["quantity"],
            "total_eur": conf["total"], "delivery_days": conf["delivery_days"],
            "payment_terms_days": conf["payment_terms_days"], "terms": list(conf["terms"]), "confirmation": conf}


def _last_sheet(events):
    for m in reversed(events):
        if m.get("from") != "buyer" and m.get("term_sheets"):
            return m["term_sheets"][0]["terms"]
    return None


def transcript(request, threads, order, names, winner):
    """Every message in the order it happened. `round` counts the buyer's messages in that supplier's thread."""
    lines, rounds = [], {sid: 0 for sid in threads}
    for sid, i in order:
        m = threads[sid][i]
        if m.get("from") == "buyer":
            rounds[sid] += 1
            kind = m["type"]
            if kind == "rfq":
                text, price = (f"Request for quote: {request['quantity']} x {request['item']}, delivery within "
                               f"{request['delivery_days']} days. Please send your unit price in EUR."), None
            elif kind == "send":
                text, price = m["body"], m["terms"]["unit_price"]
            elif kind == "accept":
                text, price = f"We accept your offer {m['term_sheet_id']}. Please confirm the order.", None
            else:
                reason = f"we placed the order with {names[winner]}" if winner else "no offer met our limits"
                text, price = f"Thank you for your offers. We will not proceed with you: {reason}.", None
            sender = "buyer"
            reply = threads[sid][i + 1] if i + 1 < len(threads[sid]) else {}
            if reply.get("from") != "buyer" and "sent_text" in reply:  # a free-text supplier got the text it was sent
                text = reply["sent_text"]
        else:
            sheets, conf = m.get("term_sheets") or [], m.get("confirmation")
            text = conf["text"] if conf else m.get("raw_text", m.get("body", ""))
            price = conf["unit_price"] if conf else (sheets[0]["terms"]["unit_price"] if sheets else None)
            sender = "supplier"
        line = {"round": rounds[sid], "supplier": names[sid], "from": sender, "text": text, "unit_price_eur": price}
        if sender == "supplier" and "raw_text" in m:  # what a free-text supplier wrote, next to what was read
            line["read_error"] = m.get("read_error")
        lines.append(line)
    return lines


def negotiate(request_text, seed=1, scenario="normal", llm=None, paid=False, tactician=False):
    """`llm` is None with the LLM flag off (the run is then the same as on `negotiation-coworker`), else an
    `llm.Client` for the free-text suppliers a `supplier_channel` line asks for. `paid` refuses free-text suppliers.
    `tactician` (needs `llm`) lets the model pick among code-priced offers (`tactician.py`)."""
    request, errors = parse_request(request_text)
    if scenario == "above_cap" and (request.get("supplier_quotes") or any("supplier_quote" in e for e in errors)):
        errors.append("scenario above_cap cannot be combined with supplier_quote lines")
    channel = "protocol"
    if llm is not None:
        channel, channel_error = parse_channel(request_text)
        if channel_error:
            errors.append(channel_error)
        elif channel != "protocol" and paid:
            errors.append(f"supplier_channel {channel} is demo only and not allowed while paid tasks are enabled")
    if errors:
        result = {
            "status": "invalid_request",
            "request": request,
            "quote": None,
            "opening_best_unit_price_eur": None,
            "winner_opening_unit_price_eur": None,
            "savings_eur": 0.0,
            "checks": [],
            "transcript": [],
            "errors": errors,
            "opening_prices_source": "simulated",
            "log_hash": None,
            "public_keys": {},
        }
        if llm is not None:
            result["llm"] = llm.usage()
        result["summary_markdown"] = summary_markdown(result)
        return result

    rng = random.Random(seed)
    quotes = request.get("supplier_quotes") or [None] * len(PERSONAS)
    suppliers = {p.sid: Supplier(p, request, rng, scenario, seed, q) for p, q in zip(PERSONAS, quotes)}
    names = {sid: s.name for sid, s in suppliers.items()}
    free = {p.sid for p in PERSONAS} if channel == "free_text" else {PERSONAS[0].sid} if channel == "mixed" else set()
    seats = {sid: FreeTextAdapter(sid, names[sid], ProseSupplier(s, seed), llm, request) if sid in free else s
             for sid, s in suppliers.items()}
    buyer = Tactician(Buyer(request), llm) if tactician and llm is not None else Buyer(request)
    out = table.run(buyer, seats, request, time_limit_s=TIME_LIMIT_S)
    threads, qty = out["threads"], request["quantity"]

    openings = {sid: pr.opening(events)[1] for sid, events in threads.items()}
    public_keys = {sid: s.public_key for sid, s in suppliers.items() if sid not in free}  # a free-text one has none
    fit = [t["unit_price"] for t in openings.values() if t and not eligible(request, t)]
    opening_best = min(fit or [t["unit_price"] for t in openings.values() if t], default=None)

    winner = out["supplier_id"] if out["outcome"] == "accepted" else None
    if winner:
        conf = out["confirmation"]
        candidate = _from_confirmation(conf) if conf else _offer(names[winner], out["terms"])
        candidate_sid = winner
    else:
        standing = {sid: _last_sheet(events) for sid, events in threads.items()}
        pool = {sid: t for sid, t in standing.items() if t and not eligible(request, t)} or \
            {sid: t for sid, t in standing.items() if t}
        candidate_sid = min(pool, key=lambda s: pool[s]["unit_price"], default=None)
        candidate = _offer(names[candidate_sid], pool[candidate_sid]) if candidate_sid is not None else None

    winner_opening = openings[candidate_sid]["unit_price"] if candidate_sid is not None else None
    accepted = {"term_sheet_id": out["term_sheet_id"], "terms": out["terms"]} if winner else None
    checks = run_checks(request, candidate, opening=winner_opening, public_key=public_keys.get(candidate_sid),
                        accepted=accepted, channel="free_text" if candidate_sid in free else "protocol") if candidate else []
    is_deal = bool(winner) and all(c["passed"] for c in checks)

    result = {
        "status": "deal" if is_deal else "no_deal",
        "request": request,
        "quote": candidate if is_deal else None,
        "opening_best_unit_price_eur": opening_best,
        "winner_opening_unit_price_eur": winner_opening if is_deal else None,
        "savings_eur": round((winner_opening - candidate["unit_price_eur"]) * qty, 2) if is_deal else 0.0,
        "checks": checks,
        "transcript": transcript(request, threads, out["order"], names, winner if is_deal else None),
        "opening_prices_source": "provided" if request.get("supplier_quotes") else "simulated",
        "log_hash": out["log_hash"],
        "public_keys": {names[sid]: key for sid, key in public_keys.items()},
    }
    if llm is not None:
        result["supplier_channels"] = {names[sid]: "free_text" if sid in free else "protocol" for sid in suppliers}
        result["llm"] = llm.usage()
        if isinstance(buyer, Tactician):
            result["tactician"] = [{"supplier": names[e["supplier_id"]], **{k: v for k, v in e.items() if k != "supplier_id"}}
                                   for e in buyer.log]
    result["summary_markdown"] = summary_markdown(result, candidate)
    return result
