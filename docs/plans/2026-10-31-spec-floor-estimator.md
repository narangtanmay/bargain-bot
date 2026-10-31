# Spec: online supplier-floor estimator (opt-in, ~1.5-2 h, freeze 12:30 CET)

Repo: app/negotiator @ 24cd832. No new dependency (requirements.txt has only `cryptography`), so pure Python.

## What the suppliers really do (shapes the design)
`suppliers.py` price at round r is `floor*(1+fm) + floor*(m0-fm)*(1-r/R)^power`. It is a pure function of the round, not of our offers. It decays toward `floor*(1+final_markup)`, so the fitted asymptote is the supplier's final price, not its floor. Call it `L` (the "floor estimate"). It over-estimates the true floor by 2-5%. A supplier accepts any offer >= its next price, and the deal then closes at our offer. So an accurate forecast of its next price is what helps us, and the margin below should be small.

## Algorithm (`negotiator/floor_model.py`, ~50 lines)
`fit(prices) -> dict | None` where `prices = [p0..pn-1]` is `side.theirs` (theirs[0] is the opening quote).
Model: `p_t = L + a*r^t`, with 0 < r < 1 and a > 0.
1. n < 3, or any non-finite price, or prices not non-increasing: return None (reason "too few points" / "bad history").
2. n == 3: closed form (Aitken). With d1 = p1-p0 and d2 = p2-p1, require d1 < 0 and d2 < 0, and r = d2/d1 in (0.05, 0.98). Otherwise None with reason "linear/no decay" (this covers equal steps and d2/d1 >= 0.98).
   Then `L = p2 - d2*r/(1-r)`, which is `p2 - d2^2/(d2-d1)`.
3. n >= 4: grid r = 0.05, 0.10, ..., 0.95. For each r, the least squares for (L, a) is linear in x_t = r^t (ordinary regression of p on x). Keep the r with the smallest SSE. Reject if a <= 0 or L <= 0.
4. Uncertainty: `sigma = max(rmse, 0.25*(p_last - L))`. At n=3 the fit is exact, so the second term is used. Return `{"L":..,"sigma":..,"r":..,"n":..}`.

Worked example. Take `[5.00, 4.60, 4.30]`. d1 = -0.40, d2 = -0.30, r = 0.75, L = 4.30 - 0.09/0.10 = **3.40**. Check: a = 1.6, and 3.4 + 1.6*0.75 = 4.60 and 3.4 + 1.6*0.5625 = 4.30. Both match. sigma = 0.25*0.90 = **0.225**.
Supplier A as quoted, `[4.88, 4.73, 4.58]`: d1 = d2 = -0.15, so r = 1, which is linear. The result is None, reason "linear/no decay", and the plain ladder is used. This is correct, because 3 collinear points carry no asymptote information.

## Where it plugs in
`Buyer.next_price(side)` in `buyer.py`. After `price = min(price, side.ceiling, theirs*UNDERCUT)` and before `cents_down`:
```python
if self.floor_model:
    price = self.floor_aim(side, price)   # returns price unchanged on any problem
```
```python
def floor_aim(self, side, ladder) -> float:
    self._floor_why = None
    try:
        est = floor_model.fit(side.theirs)
        if est is None or est["sigma"] > 0.05*est["L"]:
            self._floor_why = {"used": False, "reason": ...}; return ladder
        target = est["L"]*(1+MARGIN)
        price = min(ladder, max(target, ladder*(1-MAX_LOWER)))
        if side.ours: price = max(price, min(side.ours[-1], side.ceiling))   # never below own last offer
        price = min(price, side.ceiling)                                      # never above ceiling/cap
        self._floor_why = {"used": True, "L": .., "sigma": .., "r": .., "n": .., "target": .., "ladder": ladder, "reason": "..."}
        return price
    except Exception as e:                      # fail-safe, like tactician/llm
        self._floor_why = {"used": False, "reason": f"error {type(e).__name__}"}; return ladder
```
Constants: `MARGIN = 0.02`, `MAX_LOWER = 0.03`, sigma gate 5%. The feature can only lower an offer relative to the ladder (by <= 3%). It never raises one. The risks are a slower close and a supplier hitting its final offer.
Flag: `NEGOTIATOR_FLOOR_MODEL`. Read it in `Buyer.__init__(request, round_limit=..., floor_model=None)`, with `None` meaning `os.environ.get(...).strip().lower() == "on"`. This is the same shape as `llm.enabled` and the tactician flag. Tests pass `floor_model=True/False` directly.
The supplier's floor is never read. The estimator sees only `side.theirs`, which comes from protocol messages.

## Trace
In `Buyer.offer()`, `send()` builds `why`. When the flag is on, add `"floor_model": self._floor_why` to the `why` extras: `{"floor_model": {...}} if self.floor_model else {}`. With the flag off the dict is unchanged, so the bytes and `log_hash` are identical. The "why" string is `reason`, for example "aim 3.47 = L 3.40*(1.02); ladder 3.58; lowered 3.1%". Do not touch the `last_call_offer` or accept paths.

## Tests (`tests/test_floor_model.py`; pytest.ini already exists)
Literal values:
- `fit([5.00,4.60,4.30])` gives L == 3.40 (approx 1e-9), r == 0.75, sigma == 0.225.
- `fit([4.88,4.73,4.58])` is None, reason "linear/no decay". `fit([5.0,4.9])` is None. `fit([5,4.6,4.8])` is None.
- n=5 noiseless data from L=3.40, a=1.6, r=0.75 gives L within 0.05.
- `floor_aim`: ladder 4.00, L 3.40, MARGIN 0.02 gives target 3.468. The ladder*(1-0.03) bound is 3.88, so the result is 3.88. With ours[-1] = 3.95 the result is 3.95. With ceiling 3.90 the result is <= 3.90.
- A monkeypatched `fit` that raises gives the ladder price and `used False`.
- Flag off: existing `tests/test_flag_off.py::test_flag_off_writes_the_same_bytes_as_main` (the sha256 pins) must pass untouched. Also run `tests/test_tactician.py` (the `log_hash` equality tests). Add one test that sets the flag to "off" and "" and checks the same digests.
- Flag on: for seeds 1..20, assert `accept_gate` invariants (price <= cap, below opening, savings > 0) and that no buyer price is above `side.ceiling`. Also assert that no trace has a `floor_model` entry with `used True` and n < 3.
- A static check that `floor_model.py` and `floor_aim` never mention `_floor`: `assert "_floor" not in Path(...).read_text()`.

## Evaluation (offline script, not shipped; ~30 min)
Extend `consistency_check.py`'s loop into `eval_floor.py`. Use `range(1, 201)`, all three scenarios, with `NEGOTIATOR_FLOOR_MODEL` unset (plain) versus `on` (the same seed in both runs, so the comparison is paired). Metrics per arm:
1. Deal rate (status == "deal").
2. Mean % below the winner's opening, i.e. the existing `saving_pct_vs_winner_opening`.
3. Share of seller room captured = (opening - price)/(opening - true_floor). The evaluation script alone may read the true floor, via the supplier objects `table.run` builds. The buyer never does. If the floor is awkward to reach, use the seed's reconstructed floor from the `suppliers.py` rng. Report the mean and the paired difference with a 95% bootstrap CI.
4. Also report the buyer messages per run and the rule violations (must be 0).
Optionally add the estimator's mean absolute error of L against `floor*(1+final_markup)`.

NegMAS: on `origin/negmas-suppliers` (`negmas_suppliers.py`, `tests/test_negmas.py`), run the same two arms against the NegMAS sellers. I have not read how that branch is invoked, so check it first. Those sellers' concession curves are not exactly exponential, so this is the more honest test. Label every result "self-simulation / NegMAS dev comparison, not a benchmark".

## Keep it OFF if
- The deal-rate drop is more than 1 point, or any rule violation appears. This is a hard fail.
- The paired CI on "% below opening" or on "room captured" includes 0, or the gain is under about 0.3 pt. Then it is noise and the flag stays off.
- It wins on the simulated suppliers (which were built with a smooth decay and so favour an exponential fit) but not on the NegMAS sellers. That is a result of our own simulator, not evidence of real skill.
- The estimator mean absolute error on L is larger than the gain it buys.
Only a gain that holds on both supplier sets, with an unchanged deal rate, justifies the "on" default, and even then ship it as opt-in for the demo.
