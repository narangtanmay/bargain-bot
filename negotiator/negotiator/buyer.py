"""Buyer side. It sees only the caller's request and the supplier threads, never a supplier's internals.

The negotiation policy adapts the upstream buyer-agent engine for a price-only problem
(https://github.com/Jaseelkt007/tacto-buyer-agent, buyer policy module, MIT, Copyright (c) 2026
Tacto Technology GmbH). Kept: the price ladder (`next_price`), readiness (`ready`), the reverse auction
(`rfq_close`, `last_call_offer`), dropping bidders that cannot win, final-offer discipline, rival-offer citation
(`rival`) and the closing move (`arena_kit/play.py` `closing_move`). Dropped: total-cost terms, term trades,
clauses, supplier dossiers, data claims, e-mail signal reading and every LLM stage. Every price is set here, in code.
"""

import math
from dataclasses import dataclass, field

from . import protocol as pr
from .checks import effective_cap, terms_checks

ANCHOR = 0.80  # first offer as a share of its opening quote (the upstream policy's "leverage" anchor)
STEP, HOLD_STEP = 0.30, 0.10  # share of the gap we close per round; after a deep drop, hold
DEEP_DROP = 0.06  # a counter this far down signals a deep floor
UNDERCUT = 0.998  # we always ask a little below its standing price
CLOSE_GAP = 0.005  # within this of our last offer counts as met, once no fresh argument is left
STRICT_MOVES = 2  # ... or once this few moves remain
DROP_GAP = 0.10  # a bidder this far above the leader gets no more rounds
AUCTION_EDGE = 0.02  # a last call asks the runner-up to beat the leader by this
AUCTION_MIN_GAIN = 0.005  # keep calling while the best price improves at least this much
AUCTION_CALLS = 4


def cents_down(x):
    return math.floor(x * 100 + 1e-9) / 100


PRICE_CHECKS = {"unit_price_within_cap", "total_within_max", "price_below_opening_quote"}


def _failed(request, terms, opening, skip=()):
    errors = list(pr.validate_terms(terms))
    if errors:
        return errors
    return [f"{name}: {detail}" for name, ok, detail in terms_checks(request, terms, opening) if not ok and name not in skip]


def eligible(request, terms):
    """Reasons a sheet cannot be taken whatever its price; [] when it can (the checker's own non-price checks)."""
    return _failed(request, terms, None, skip=PRICE_CHECKS)


def accept_gate(request, terms, opening):
    """(ok, reasons) for taking a sheet: every check in `checks.terms_checks`. The cap is inclusive; the saving is
    strict: the price must be below the supplier's own opening quote, so every deal saves the caller something."""
    reasons = _failed(request, terms, opening)
    return not reasons, reasons


def opening_price(events):
    return pr.opening(events)[1].get("unit_price")


def closing_move(request, threads):
    """Accept the cheapest standing sheet that passes the accept gate, else walk away (`play.closing_move`).
    Used when time or rounds run out and whenever the buyer's own move fails."""
    best = None
    for sid in pr.live_threads(threads):
        sheet_id, terms = pr.standing(threads[sid])
        if sheet_id and accept_gate(request, terms, opening_price(threads[sid]))[0]:
            best = min(best or (terms["unit_price"], sid, sheet_id), (terms["unit_price"], sid, sheet_id))
    if best is None:
        return {"supplier_id": None, "type": "walk_away", "why": "no standing sheet passes the accept gate"}
    price, sid, sheet_id = best
    return {"supplier_id": sid, "type": "accept", "term_sheet_id": sheet_id,
            "why": f"cheapest sheet passing the accept gate at {price:.2f}"}


@dataclass
class Side:
    sid: str
    opening: float
    ceiling: float  # the most we offer it: the cap, and a cent below its own opening quote
    ours: list = field(default_factory=list)  # our prices to it
    theirs: list = field(default_factory=list)  # its standing price after each of its messages
    replies: int = 0
    seen: int = 0  # arrival order across threads: the lowest has waited longest
    dropped: bool = False
    rival_cited: dict = field(default_factory=dict)  # rival sid -> price we cited to it


class Buyer:
    def __init__(self, request, round_limit=pr.ROUND_LIMIT):
        self.request, self.round_limit = request, round_limit
        self.sides = {}
        self.arrivals = 0
        self.rfq = False
        self.board = {}  # sid -> standing price of each eligible live supplier
        self.leader = None
        self.last_call = None  # (runner-up sid, its replies when we called, best price then)
        self.calls = 0

    # ---------- per move (`Negotiator.decide`) ----------
    def decide(self, threads):
        for sid, events in threads.items():
            if sid not in self.sides:
                price = opening_price(events)
                if price is not None:
                    cap = effective_cap(self.request)
                    self.sides[sid] = Side(sid, price, cents_down(min(cap, price - 0.01)))
        for sid in self.sides:
            self.observe(self.sides[sid], threads[sid])

        live = [s for s in pr.live_threads(threads) if s in self.sides]
        self.board = {}
        for sid in live:
            sheet_id, terms = pr.standing(threads[sid])
            if sheet_id and not eligible(self.request, terms):
                self.board[sid] = terms["unit_price"]
        active = [s for s in live if s in self.board]  # suppliers we can do business with at some price
        if not active:
            return closing_move(self.request, threads)
        self.rfq = len(active) > 1
        self.leader = min(self.board, key=self.board.get)

        offers = []
        for sid in active:
            sheet_id, terms = pr.standing(threads[sid])
            if accept_gate(self.request, terms, self.sides[sid].opening)[0]:
                offers.append((terms["unit_price"], sid, sheet_id))
        offers.sort()
        best = offers[0] if offers else None
        ready = {sid: self.ready(self.sides[sid], threads[sid]) for sid in active}

        if self.rfq:
            move = self.rfq_close(threads, active, ready, best)
            if move:
                return move
            for sid in active:  # bidders that cannot catch the leader get no more rounds
                side = self.sides[sid]
                if (sid != self.leader and len(side.theirs) >= 2 and not side.dropped
                        and self.board[sid] > self.board[self.leader] * (1 + DROP_GAP)):
                    side.dropped = True
        if best and (ready[best[1]] or all(ready.values())):
            return self.accept(best, ready[best[1]] or "every supplier is ready")
        can = [s for s in active if self.moves_left(threads[s]) > 0 and pr.latest(threads[s]).get("status") != "final_offer"]
        if not best and not can:
            return self.walk("no standing sheet passes the accept gate and no supplier can move")
        talk = [s for s in can if not ready[s] and not self.sides[s].dropped] or [s for s in can if not ready[s]] or can
        if not talk:
            return self.accept(best, "no moves left") if best else self.walk("no moves left")
        sid = min(talk, key=lambda s: self.sides[s].seen)
        return self.offer(self.sides[sid], threads[sid])

    def moves_left(self, events):
        return pr.moves_left(events, self.round_limit)

    def observe(self, side, events):
        their = [m for m in events if m.get("from") != "buyer"]
        if len(their) <= side.replies:
            return
        side.replies = len(their)
        self.arrivals += 1
        side.seen = self.arrivals
        _, terms = pr.standing(events)
        price = terms.get("unit_price")
        side.theirs.append(price if price is not None else (side.theirs[-1] if side.theirs else math.inf))

    def ready(self, side, events):
        """Is this supplier at the point where we should take its standing sheet? (`Negotiator.ready`)"""
        status, left = pr.latest(events).get("status"), self.moves_left(events)
        if status == "final_offer" or left <= 1:
            return status if status == "final_offer" else "last move"
        if status == "agreed":
            return "agreed"
        if not side.ours or not side.theirs:
            return False
        if side.theirs[-1] <= side.ours[-1]:
            return "at or below our offer"
        if side.theirs[-1] <= side.ours[-1] * (1 + CLOSE_GAP):
            if not (left > STRICT_MOVES and self.rival(side) is not None):
                return "within half a percent of our offer"
        return False

    def next_price(self, side):
        """The price ladder (`Negotiator.next_price`), price only."""
        theirs = side.theirs[-1]
        if not side.ours:
            price = min(side.opening * ANCHOR, theirs * 0.99)
        else:
            first_drop = (side.theirs[0] - side.theirs[1]) / side.theirs[0] if len(side.theirs) > 1 else 0
            last_drop = (side.theirs[-2] - side.theirs[-1]) / side.theirs[-2] if len(side.theirs) > 1 else 0
            deep = (len(side.ours) == 1 and first_drop >= DEEP_DROP) or (self.rfq and last_drop >= DEEP_DROP)
            step = HOLD_STEP if deep else STEP
            price = max(side.ours[-1] + step * (theirs - side.ours[-1]), side.ours[-1])
        price = min(price, side.ceiling, theirs * UNDERCUT)
        if side.ours:  # never step back below our own last offer
            price = max(price, min(side.ours[-1], side.ceiling))
        return max(cents_down(price), 0.01)

    # ---------- reverse auction (`Negotiator.rfq_close`, `last_call_offer`) ----------
    def rfq_close(self, threads, active, ready, best):
        """Once the leader is ready, the best runner-up is asked to beat it; while the best price keeps
        improving, the new runner-up is asked next. A bidder at final_offer is never pushed."""
        leader = self.leader
        if not best or best[1] != leader:
            return None
        if self.last_call:  # a call is out: judge it once its reply is in
            runner, replies, before = self.last_call
            if runner in active and self.sides[runner].replies <= replies:
                return None
            self.last_call = None
            self.calls += 1
            if best[0] >= before * (1 - AUCTION_MIN_GAIN) or self.calls >= AUCTION_CALLS:
                return self.accept(best, f"best after {self.calls} auction call(s)")
        elif not ready.get(leader):
            return None
        runners = [s for s in active if s != leader and self.moves_left(threads[s]) > 0 and not self.sides[s].dropped
                   and pr.latest(threads[s]).get("status") != "final_offer"]
        move = None
        if runners:
            runner = min(runners, key=self.board.get)
            move = self.last_call_offer(self.sides[runner], threads[runner])
            if move:
                self.last_call = (runner, self.sides[runner].replies, best[0])
        if move is None and self.calls:
            return self.accept(best, f"best after {self.calls} auction call(s), no runner-up left")
        return move

    def last_call_offer(self, side, events):
        lead = self.board[self.leader]
        price = cents_down(min(lead * (1 - AUCTION_EDGE), side.ceiling, side.theirs[-1] * UNDERCUT))
        if price <= 0:  # a call may ask less than our last offer to it: a rival has beaten that since
            return None
        side.rival_cited[self.leader] = lead
        body = (f"Another supplier has offered EUR {lead:.2f} per unit. If you can offer EUR {price:.2f} per unit, "
                "please send it now; otherwise we will proceed with the other offer.")
        return self.send(side, events, price, body, {"last_call": True, "leader_price": lead})

    # ---------- messages ----------
    def rival(self, side):
        """(rival sid, price) to cite to this supplier now, or None: the leader's offer, once per price."""
        rival = self.leader if self.leader and self.leader != side.sid and self.leader in self.board else None
        if rival is None or side.rival_cited.get(rival) == self.board[rival]:
            return None
        return rival, self.board[rival]

    def offer(self, side, events):
        price = self.next_price(side)
        rival = self.rival(side)
        if rival:
            side.rival_cited[rival[0]] = rival[1]
        return self.send(side, events, price, self.offer_body(price, rival[1] if rival else None),
                         {"rival": rival[1] if rival else None})

    def offer_body(self, price, rival_price):
        lines = [f"Thank you for your offer. We can offer EUR {price:.2f} per unit for {self.request['quantity']} units."]
        if rival_price is not None:
            lines.append(f"Another supplier has offered EUR {rival_price:.2f} per unit.")
        return " ".join(lines)

    def send(self, side, events, price, body, why):
        _, standing = pr.standing(events)
        terms = {**standing, "unit_price": price, "quantity": self.request["quantity"]}
        side.ours.append(price)
        return {"supplier_id": side.sid, "type": "send", "terms": terms, "body": body,
                "why": {"price": price, "their_price": side.theirs[-1], "ceiling": side.ceiling, **why}}

    def accept(self, best, why):
        price, sid, sheet_id = best
        return {"supplier_id": sid, "type": "accept", "term_sheet_id": sheet_id, "why": f"{why}; {price:.2f} passes the accept gate"}

    def walk(self, why):
        return {"supplier_id": None, "type": "walk_away", "why": why}
