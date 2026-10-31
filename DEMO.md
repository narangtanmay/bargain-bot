# Bargain Bot tactician demo

The tactician is included in `negotiation-coworker`. It remains off by default; the normal worker uses the deterministic engine unless the demo flags explicitly enable it.

The tactician lets a model choose among buyer offers that code already priced. It answers with an option ID and never writes a number. The cap, the accept gate and the checker are unchanged. It is off by default and refuses to run while `PAID_TASKS_ENABLED=true`. See `negotiator/negotiator/tactician.py`.

Label for any run with it on: **"an LLM chose among code-priced offers; it set no price"**. The run's summary prints this itself.

## 1. Plain engine (no model)

```sh
cd negotiator
python3 -m negotiator --request-file examples/request.txt --out ../.local/demo/plain-seed1.json --seed 1
```

Expected: `deal`, Supplier A at EUR 4.31, savings EUR 1,140.

## 2. Live run (DeepSeek)

Needs `DEEPSEEK_API_KEY` in `.env`. The Python CLI does not read `.env`, so load it first. Set the flags on the command line, not in `.env`: the worker passes its environment to the negotiator, so flags left in `.env` would turn the tactician on for unpaid Sokosumi Tasks too.

```sh
cd negotiator
set -a; . ../.env; set +a
NEGOTIATOR_LLM=on NEGOTIATOR_LLM_PROVIDER=deepseek NEGOTIATOR_TACTICIAN=on PAID_TASKS_ENABLED=false \
  python3 -m negotiator --request-file examples/request.txt --out ../.local/demo/live-seed1.json --seed 1
```

About 50 s and 5-8 model calls (roughly USD 0.004 at DeepSeek's off-peak list prices, an estimate, not a bill). The picks change from run to run. The model's time budget is 50 s per run, inside the table's 60 s limit. Picks that do not fit fall back to the engine's own offer (E0), so the run still ends in a deal or a `no_deal`, never an error. If the API fails, every pick falls back to E0 and the deal equals the plain engine's (same quote and `log_hash`). The summary still carries the tactician label, and its Tactician section says that every offer fell back to the engine's.

Recorded run, 2026-10-31 06:30 UTC, merge `0d3283c`, `deepseek-flash`, default effort: `deal`, Supplier A at EUR 4.16, savings EUR 1,440, 10 of 10 checks pass, 50.5 s wall. 7 offers went to the tactician: 4 valid picks (anchor75, E0, step10, step10), 1 call failed or answered late, and 2 were skipped once the budget ran out. That historical run exposed a usage-reporting bug: two budget skips were counted as failed calls. The current implementation counts only the one real failed/late call as a failure and reports budget skips separately.

## 3. Offline replay (no API, no cost)

`negotiator/examples/tactician-replay-seed1.json` holds the recorded run's answers in order: a valid pick for each of the 4 valid answers, and an empty answer, which falls back to E0, for the other 3.

```sh
cd negotiator
NEGOTIATOR_LLM=on NEGOTIATOR_LLM_PROVIDER=fake NEGOTIATOR_TACTICIAN=on \
NEGOTIATOR_LLM_FAKE_REPLIES=examples/tactician-replay-seed1.json \
  python3 -m negotiator --request-file examples/request.txt --out ../.local/demo/replay-seed1.json --seed 1
```

Expected: the recorded run's status, quote, savings, checks, transcript and `log_hash`, in well under a second. Use it as the stage backup. Call it a replay of a recorded run: it shows how the tactician steers the run, but no model judged anything this time.

## What not to claim

- EUR 4.16 against 4.31 is one seed against our own simulated suppliers, not a savings result. The suppliers concede by round count, so any slower buyer beats them by construction. A fake model that always holds "wins" too.
- The model sees prices and history only, never the cap or supplier prose.
- The tactician is disabled while `PAID_TASKS_ENABLED=true`. Its presence in the repository does not establish that a paid run used a model.
