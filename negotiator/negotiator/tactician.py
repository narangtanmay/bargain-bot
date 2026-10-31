"""A model picks the buyer's next price offer from a short list that code priced. The model never writes a number.

Pattern from the upstream hybrid tactician (buyer-agent tactician module, MIT, Copyright (c) 2026 Tacto
Technology GmbH): the engine decides first; its move is option E0; code adds a few other options, each priced from
the same ladder and limits; the model answers with one option ID; code checks it. An unknown ID, invalid JSON, a
timeout or an API failure sends E0. The upstream implementation shipped it off by default: on its arena it did not beat the rule
engine. Here it only ever touches ordinary price offers. Accepts, walk-aways and last calls stay the engine's,
every counter still passes `table.check_move` (cap, quantity, delivery, final offers), and every accept still
passes the accept gate.

The prompt carries prices and history only: never the caller's cap, and no supplier prose.
"""

import json

from . import protocol as pr
from .buyer import ANCHOR, HOLD_STEP, STEP, UNDERCUT, closing_move, cents_down

MAX_TOKENS = 120
REASON_CHARS = 160

SYSTEM = """You choose a buyer's next move in a purchase negotiation with several suppliers. Code has priced \
every option and enforces every rule; you only pick one option ID and never write a price.
The buyer wants the lowest unit price that still closes a deal. A deal must be below the supplier's own \
opening quote. Offering more closes faster but costs more; offering less saves money but may stall the \
supplier or use up the rounds left. "hold" repeats our last offer. "accept" takes that sheet now and ends \
the negotiation. E0 is the default rule engine's move; it is a valid choice.
Reply with one JSON object only: {"option": "<option id>", "reason": "<one short sentence>"}"""


def _clip(side, price, prev):
    """The engine's own limits on a price to this supplier (`Buyer.next_price`)."""
    price = min(price, side.ceiling, side.theirs[-1] * UNDERCUT)
    if prev:
        price = max(price, min(prev[-1], side.ceiling))
    return max(cents_down(price), 0.01)


class Tactician:
    """Wraps a `Buyer`: `decide(threads)` returns the engine's move, or the option the model picked."""

    def __init__(self, buyer, client):
        self.buyer, self.client = buyer, client
        self.log = []

    def options(self, threads, move):
        """{option id: (kind, price or sheet)} for this offer; E0 is the engine's move."""
        side = self.buyer.sides[move["supplier_id"]]
        prev, opening, theirs = side.ours[:-1], side.opening, side.theirs[-1]  # `send` already logged E0's price
        p0 = move["terms"]["unit_price"]
        rungs = {}
        if not prev:
            for share in (ANCHOR - 0.05, ANCHOR + 0.05):
                rungs[f"anchor{round(share * 100)}"] = _clip(side, min(opening * share, theirs * 0.99), prev)
        else:
            rungs["hold"] = _clip(side, prev[-1], prev)
            for share in (HOLD_STEP, STEP + 0.20):
                rungs[f"step{round(share * 100)}"] = _clip(side, prev[-1] + share * (theirs - prev[-1]), prev)
        options = {"E0": ("send", p0)}
        for oid, price in rungs.items():
            if all(price != p for kind, p in options.values() if kind == "send"):
                options[oid] = ("send", price)
        close = closing_move(self.buyer.request, threads)
        if close["type"] == "accept":
            sid, sheet_id = close["supplier_id"], close["term_sheet_id"]
            options["accept"] = ("accept", (sid, sheet_id, pr.standing(threads[sid])[1]["unit_price"]))
        return options

    def packet(self, threads, move, options):
        sid = move["supplier_id"]
        side, events = self.buyer.sides[sid], threads[sid]
        others = {s: p for s, p in self.buyer.board.items() if s != sid}
        lines = [
            f"Supplier {sid}: status {pr.latest(events).get('status')}, "
            f"{pr.moves_left(events, self.buyer.round_limit)} buyer messages left in its thread.",
            f"Its opening quote: EUR {side.opening:.2f}. Its prices so far: "
            + ", ".join(f"EUR {p:.2f}" for p in side.theirs) + ".",
            "Our offers to it so far: " + (", ".join(f"EUR {p:.2f}" for p in side.ours[:-1]) or "none") + ".",
            "Other suppliers' standing prices: " + (", ".join(f"{s} EUR {p:.2f}" for s, p in sorted(others.items()))
                                                    or "none") + ".",
            "Options:",
        ]
        for oid, (kind, value) in options.items():
            if kind == "send":
                lines.append(f"- {oid}: offer EUR {value:.2f} per unit to supplier {sid}")
            else:
                lines.append(f"- {oid}: accept supplier {value[0]}'s standing sheet at EUR {value[2]:.2f} now")
        return "\n".join(lines)

    def _pick(self, reply, options):
        """(option id, reason, None) for a valid answer, else (None, None, why not)."""
        if not isinstance(reply, str) or "{" not in reply:
            return None, None, "no answer" if reply is None else "no JSON"
        try:
            data = json.loads(reply[reply.index("{"):reply.rindex("}") + 1])
        except ValueError:
            return None, None, "invalid JSON"
        oid = data.get("option") if isinstance(data, dict) else None
        if not isinstance(oid, str) or oid not in options:
            return None, None, f"unknown option {oid!r}"
        reason = data.get("reason")
        return oid, " ".join(reason.split())[:REASON_CHARS] if isinstance(reason, str) else "", None

    def decide(self, threads):
        move = self.buyer.decide(threads)
        if move.get("type") != "send" or (move.get("why") or {}).get("last_call"):
            return move
        options = self.options(threads, move)
        if len(options) < 2:
            return move
        reply = self.client.complete(SYSTEM, self.packet(threads, move, options), max_tokens=MAX_TOKENS)
        oid, reason, fallback = self._pick(reply, options)
        self.log.append({"supplier_id": move["supplier_id"],
                         "options": {o: v if k == "send" else "accept" for o, (k, v) in options.items()},
                         "chosen": oid or "E0", "fallback": fallback, "reason": reason})
        if oid is None or oid == "E0":
            return move
        kind, value = options[oid]
        why = {**move["why"], "tactician": oid, "engine_price": move["terms"]["unit_price"]}
        if kind == "accept":  # ends the negotiation, so the engine's record of E0 needs no undoing
            sid, sheet_id, price = value
            return {"supplier_id": sid, "type": "accept", "term_sheet_id": sheet_id,
                    "why": f"tactician: accept at {price:.2f} instead of offering {move['terms']['unit_price']:.2f}"}
        side = self.buyer.sides[move["supplier_id"]]
        side.ours[-1] = value  # the engine logged E0's price; it now remembers the price actually sent
        why["price"] = value
        return {**move, "terms": {**move["terms"], "unit_price": value},
                "body": self.buyer.offer_body(value, move["why"].get("rival")), "why": why}
