"""Baseline buyer for comparison only: the policy of this project's first engine (`a538ade`, `engine.py`), restated
as a protocol buyer so it runs on the same table, suppliers and accept gate as the ported ProcuDeal buyer.

Policy, unchanged: three counter rounds after the RFQ. Each round the current leader is asked for 5% below its own
price (capped), and every other eligible supplier for one cent below the leader (capped). Then it takes the
cheapest standing sheet that passes the accept gate, else walks away. No ladder, no readiness, no auction.
Not used by the product; `consistency_check --buyer baseline` selects it.
"""

from . import protocol as pr
from .buyer import cents_down, closing_move, effective_cap, eligible

MAX_ROUNDS = 4  # RFQ round plus three counter rounds, as in `a538ade`
LEADER_ASK = 0.95


class BaselineBuyer:
    def __init__(self, request, round_limit=pr.ROUND_LIMIT):
        self.request, self.round = request, 1
        self.queue = []

    def decide(self, threads):
        if not self.queue:
            if self.round >= MAX_ROUNDS:
                return closing_move(self.request, threads)
            self.round += 1
            board = {}
            for sid in pr.live_threads(threads):
                sheet_id, terms = pr.standing(threads[sid])
                if sheet_id and not eligible(self.request, terms) and pr.latest(threads[sid]).get("status") != "final_offer":
                    board[sid] = terms
            if not board:
                return closing_move(self.request, threads)
            cap = effective_cap(self.request)
            leader = min(board, key=lambda s: board[s]["unit_price"])
            lead = board[leader]["unit_price"]
            for sid, terms in board.items():
                if sid == leader:
                    target = cents_down(min(terms["unit_price"], cap) * LEADER_ASK)
                    body = f"Your offer is currently the best we have. To award the order we need EUR {target:.2f} per unit."
                else:
                    target = cents_down(min(lead - 0.01, cap))
                    body = f"Another supplier has offered EUR {lead:.2f} per unit. Can you offer EUR {target:.2f} or better?"
                self.queue.append((sid, {**terms, "unit_price": target, "quantity": self.request["quantity"]}, body))
        sid, terms, body = self.queue.pop(0)
        if sid not in pr.live_threads(threads):
            return self.decide(threads)
        return {"supplier_id": sid, "type": "send", "terms": terms, "body": body, "why": {"baseline_round": self.round}}
