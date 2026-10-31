"""Rephrases a buyer message the buyer has already built, with the model as an untrusted copywriter.

The price is fixed before the writer runs: `buyer.py` set it and the structured terms carry it, so the writer
only changes wording. Code guards the wording: every number in the output must be the chosen price, the cited
rival price, the quantity or the delivery days; the chosen price must appear in EUR (and the rival price, if the
template cites one); and the output must not mention a cap, a budget, urgency, finality, or a rival that "agreed".
Any failed guard or model failure keeps the template text unchanged.
"""

import re

from .reader import NUMBER, parse_number

MAX_TOKENS = 200
MAX_CHARS = 600

SYSTEM = """You rewrite a buyer's message to a supplier so it reads naturally and politely, as a short business \
e-mail body. Keep its meaning exactly.
- Use only the numbers in the original message, written the same way, and no other numbers or number words.
- Do not add any claim, promise, deadline or reason that is not in the original.
- Never mention a budget, a price limit, urgency, or that anything is final or agreed.
- Reply with the rewritten message only: no greeting line with a name, no signature, no quotes around it."""

FORBIDDEN = re.compile(
    r"\b(cap|caps|capped|budget\w*|limit\w*|max|maximum|ceiling|afford\w*|urgent\w*|asap|rush\w*|desperate\w*|"
    r"final\w*|last offer|best and final|agree\w*|accept\w*|committed|signed|contract\w*|percent|per cent|"
    r"zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|hundred\w*|"
    r"thousand\w*|million\w*|dozen\w*|half)\b|%|https?:|@")
EUR_NEAR = re.compile(r"(\beur(?![a-z])|€|\beuros?\b)")


def _same(a, b):
    return abs(a - b) < 1e-9


def check(text, *, price, rival, quantity, delivery_days, rival_required):
    """None if `text` may go out, else why not."""
    if not isinstance(text, str) or not text.strip():
        return "empty"
    if len(text) > MAX_CHARS:
        return "too long"
    low = text.casefold()
    bad = FORBIDDEN.search(low)
    if bad:
        return f"mentions {bad.group(0)!r}"
    allowed = [v for v in (price, rival, quantity, delivery_days) if v is not None]
    seen_price = seen_rival = False
    for m in NUMBER.finditer(low):
        value = parse_number(m.group(0))
        if value is None:  # `2,000`: allowed only as the quantity
            digits = re.sub(r"\D", "", m.group(0))
            if int(digits) != quantity:
                return f"number {m.group(0)!r} is ambiguous"
            value = quantity
        if not any(_same(value, a) for a in allowed):
            return f"number {m.group(0)!r} is not in the buyer's message"
        in_eur = bool(EUR_NEAR.search(low[max(0, m.start() - 6):m.end() + 8]))
        seen_price |= in_eur and _same(value, price)
        seen_rival |= in_eur and rival is not None and _same(value, rival)
    if not seen_price:
        return "chosen price missing"
    if rival_required and not seen_rival:
        return "rival price missing"
    return None


def _clean(reply):
    text = (reply or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def write(client, body, *, price, rival=None, quantity, delivery_days):
    """(text to send, reason). `reason` is None when the model's wording passed every guard, else why the template
    `body` is sent instead. `price` and `rival` come from the buyer's move (`why`), never from the model."""
    if client is None:
        return body, "no model configured"
    rival_required = rival is not None and f"{rival:.2f}" in body
    text = _clean(client.complete(SYSTEM, f"Original message:\n<<<\n{body}\n>>>", max_tokens=MAX_TOKENS))
    reason = check(text, price=price, rival=rival, quantity=quantity, delivery_days=delivery_days,
                   rival_required=rival_required)
    return (body, reason) if reason else (text, None)
