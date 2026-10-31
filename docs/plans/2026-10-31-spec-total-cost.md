# Spec: thin total-cost port (negotiator @ 24cd832)

## Source formula (MIT, Tacto; cite in cost.py docstring)
- Tacto `brief/api.md` L390-393 (also `brief.md` L125-156), `starter-kit/arena_kit/cost.py` L151-152 (repo Jaseelkt007/tacto-buyer-agent, same file in tacto-playground kit):
  - `payment_terms = spend * r * (d_ref - payment_days) / 360` (paying earlier than reference costs interest; later saves it)
  - `freight = committed * freight_eur_per_unit[incoterm]` (L152). We have no freight data in our protocol: SKIP, say so.
  - `C = spend + payment_terms (+ freight, late, quality... skipped)`; `spend = units * unit_price`.
- Score: `api.md` L420-426, `cost.py` L170-175: `S = clip((C_open - C_deal)/(C_open - C_best), 0, 1)`; if `C_open - C_best <= 0.01`, S=1 only when deal <= C_best. C_open = cheapest opening quote's C; C_best = hidden: best package any supplier would ever accept, or your alternative.
- Worked example (brief.md L153-156): 8000 x 43.20 + 8000x43.20x0.08x30/360 = 347,904.

## C_best honesty
The buyer cannot see supplier floors, so C_best is unknowable here (only the arena knows it). Do NOT print S. Print the buyer-side numbers only: C_open (cheapest opening total cost), C_deal, saving = C_open - C_deal (EUR and %), plus saving vs the winner's own opening (same meaning as today's `savings_eur`). A "best observed" C_best would give S=1 whenever we take the cheapest standing offer: flattering and false. Put the S formula in a docstring only.

## Slice 1: cost model (~45 min, no behaviour change)
Files:
- `negotiator/cost.py` (new): `total_cost(terms, request) -> float` = `round(unit_price*quantity*(1 + r/100*(d_ref - payment_terms_days)/360), 2)`; `effective_unit(terms, request) -> float` (same / quantity, unrounded); `enabled(request) -> bool` (`"financing_rate_pct" in request`).
- `request.py` `parse_request`: add keys to the `OPTIONAL` loop. `financing_rate_pct`: float, 0 < x <= 100. `reference_payment_days`: int, 1..365, default 30. Only when the line is present put BOTH keys in `request` (absent -> request dict unchanged, so `result["request"]` stays identical). Error if `reference_payment_days` is given without a rate. Also add both to `json_request_text` key loop.
- `engine.py`: after `candidate` is built, only `if cost.enabled(request)`: add `result["total_cost"] = {"opening_best_eur", "winner_opening_eur", "deal_eur", "saving_eur", "saving_pct", "reference_payment_days", "financing_rate_pct"}`. Opening terms come from `pr.opening(events)[1]`. Add the key only when on.
- `summary.py`: in `summary_markdown`, after the "## Price" block, add a "## Total cost" section only when `result.get("total_cost")`. Label: "model: purchase cost + payment-term financing vs a reference term; freight and delivery are not modelled; not a verified price".
Flag-off proof: existing `tests/test_flag_off.py::test_flag_off_writes_the_same_bytes_as_main` (MAIN_DIGESTS, 15 request/seed pairs) must pass untouched.
Tests (new `tests/test_cost.py`; AAA, req = qty 2000, r=8, ref 30):
- 4.50, net 45 -> `8970.00`; 4.50, net 14 -> `9032.00`; 4.50, net 30 -> `9000.00`.
- r=24: 4.26 qty 2000 net 60 -> `8349.60`; 4.21 net 30 -> `8420.00`.
- parse: `financing_rate_pct: 8` -> `{8.0, 30}`; `-1`, `abc`, `101` -> error; `reference_payment_days: 45` alone -> error; no line -> `"financing_rate_pct" not in request`.
- With the line added to examples/request.txt, seed 1: `log_hash` equals the flag-off run (flow unchanged), `total_cost.deal_eur == 8620.00` (A 4.31 net 30), result has the extra key, and the summary contains "## Total cost".
Demo text: examples/request.txt plus `financing_rate_pct: 8`.
Risks: float rounding (round only at the end); `negotiate.mjs` needs no change in slice 1.

## Slice 2: decide on total cost (~45 min)
Behaviour only when `cost.enabled(request)`; else code paths are the same.
- `buyer.py`: in `decide`, keep `self.board` as raw unit prices (they are cited to rivals and drive the ladder, so caps and `ceiling` are unchanged). Add `self.rank = {sid: cost.effective_unit(terms, request)}`. Use `rank` (when on) for: `self.leader = min(...)`, the `offers.sort()` key, `closing_move`'s `min` key, and the `AUCTION_MIN_GAIN` comparison in `rfq_close` (compare effective cost). Helper `_key(terms)` returns `effective_unit` if on else `unit_price`; flag off returns the unit price, so nothing changes.
- `last_call_offer`: ask the runner-up to beat the leader's effective cost: `price = cents_down(min(lead_eff*(1-AUCTION_EDGE)/factor_runner, ceiling, theirs*UNDERCUT))`, `factor = 1 + r/100*(d_ref-days)/360`. The message still cites the leader's real unit price.
- ONE new check `total_cost_below_opening` (detail e.g. `8349.60 vs opening 8520.00`): add in `checks.run_checks` as the LAST item (position 11) only when on, taking a new `opening_terms=None` arg; engine passes `pr.opening(...)[1]`. Also run it in `buyer._failed` (gate) so the checker never rejects what the gate accepted. No payment change (a hash is submitted only on a deal).
- The 10-check list is hard-coded in: `negotiate.mjs` L10 (`CHECK_NAMES`) and L24 (requires `checks.length === CHECK_NAMES.length` and every name in order, else a deal is rejected as "did not pass the complete verification contract"), `CONTRACT.md` L90, `tests/test_negotiator.py` L10/66/287, `test-fixtures/verified-result.mjs`, `unpaid-workflow.integration.mjs` L5/39. Change: keep the 10 names and order; in `negotiate.mjs` accept an optional 11th `total_cost_below_opening` (must pass if present); document in CONTRACT.md. Flag-off results stay at 10.
- Persona effect: today A net 30, B net 45, C net 14 (suppliers.py `payment_terms_days`). B vs A is only 15 days = 0.33% of price at 8%; a flip needs a unit gap under 0.33% (seeds 1-6 show gaps of 1-25%, so no visible difference). Minimal change: in `engine.negotiate`, only when on, `dataclasses.replace(PERSONAS[1], payment_terms_days=60)` (do not edit the PERSONAS tuple: flag-off bytes, hash test). Then at r=24, B vs A is 2%: seed 3 pair A 4.21 (net 30) vs B 4.26 (net 60) gives 8420.00 vs 8349.60, so B is pricier per unit and cheaper overall. Use the numbers as an illustration: the buyer's path changes, so run seeds 1-10 with the demo text and pick one that shows the flip. Do not claim savings from one seed. B's 60 days still passes `payment terms net 30`.
Tests:
- Unit (build `Buyer` threads by hand, like tests/test_buyer.py): A 4.21 net 30 vs B 4.26 net 60, r=24, ref 30 -> `leader == "B"`; with the line off -> `leader == "A"`. `closing_move` accepts B when on, A when off.
- `run_checks` with the line: 11 checks, last name `total_cost_below_opening`; without it, 10 checks and the `CHECK_NAMES` equality in test_negotiator.py still holds.
- Cap invariant: with r=24, no sent `unit_price` exceeds `effective_cap` (loop seeds 1-10).
- Flag-off hash test unchanged.
- Run `node` tests for negotiate.mjs (accepts 10 and 11 checks).
Demo text: request.txt plus `financing_rate_pct: 24` and `reference_payment_days: 30`.
Risks: ladder compares raw prices while the leader is chosen by effective cost (a leader may have the higher raw price; fine, caps hold); `AUCTION_MIN_GAIN` logic is the delicate part; 11th check is redundant for the final price while payment days are constant per supplier (say so); persona override is simulation, label it MOCKED in summary.
