"""Self-simulation consistency check: run the negotiator over many seeds and scenarios and count outcomes.

This is NOT a benchmark. With the default suppliers this team wrote both the buyer and the sellers, so the numbers
show that the rules hold and the outcomes are stable. With `--suppliers negmas` (dev only) the sellers are NegMAS
strategies this team did not write, but we still choose their reservation prices.

`margin_captured_pct` is how much of the winner's room between its opening quote and its hidden reservation price
the buyer won. The check reads the reservation prices by rebuilding the suppliers from the seed; the buyer never
sees them.

    cd negotiator && python3 -m negotiator.consistency_check [--request examples/request.txt] [--seeds 200]
                                                             [--suppliers simulated|negmas] [--buyer ported|baseline]
"""

import argparse
import json
import statistics
import time
from pathlib import Path

from .engine import make_suppliers, negotiate
from .request import parse_request

SCENARIOS = ("normal", "above_cap", "broken_quote")


def check(text, seeds, model="simulated", buyer="ported"):
    out = {}
    for scenario in SCENARIOS:
        statuses, savings, captured, rounds, seconds, violations, winners = {}, [], [], [], [], 0, []
        for seed in range(seeds):
            t0 = time.perf_counter()
            r = negotiate(text, seed=seed, scenario=scenario, suppliers=model, buyer=buyer)
            seconds.append(time.perf_counter() - t0)
            statuses[r["status"]] = statuses.get(r["status"], 0) + 1
            rounds.append(sum(1 for m in r["transcript"] if m["from"] == "buyer"))
            if r["status"] == "deal":
                q = r["quote"]
                winners.append(q["supplier"])
                opening = r["winner_opening_unit_price_eur"]
                savings.append(100 * (opening - q["unit_price_eur"]) / opening)
                winner = next(s for s in make_suppliers(parse_request(text)[0], seed, scenario, model).values()
                              if s.name == q["supplier"])
                if opening > winner._floor:
                    captured.append(100 * (opening - q["unit_price_eur"]) / (opening - winner._floor))
                if not (q["unit_price_eur"] <= r["request"]["max_unit_price_eur"]
                        and q["unit_price_eur"] < r["winner_opening_unit_price_eur"] and r["savings_eur"] > 0):
                    violations += 1
        out[scenario] = {
            "runs": seeds,
            "statuses": statuses,
            "rule_violations": violations,
            "saving_pct_vs_winner_opening": {
                "mean": round(statistics.mean(savings), 1), "min": round(min(savings), 1), "max": round(max(savings), 1)
            } if savings else None,
            "margin_captured_pct": {
                "mean": round(statistics.mean(captured), 1), "min": round(min(captured), 1), "max": round(max(captured), 1)
            } if captured else None,
            "winners": dict(sorted({w: sum(1 for x in winners if x == w) for w in set(winners)}.items())),
            "buyer_messages_per_run_mean": round(statistics.mean(rounds), 1),
            "ms_per_run_mean": round(1000 * statistics.mean(seconds), 1),
        }
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(prog="negotiator.consistency_check", description=__doc__.split("\n")[0])
    parser.add_argument("--request", type=Path, default=Path("examples/request.txt"))
    parser.add_argument("--seeds", type=int, default=200)
    parser.add_argument("--suppliers", choices=("simulated", "negmas"), default="simulated")
    parser.add_argument("--buyer", choices=("ported", "baseline"), default="ported",
                        help="baseline: the first engine's policy (a538ade), for comparison only")
    args = parser.parse_args(argv)
    kind = ("self-simulation consistency check (not a benchmark: same team wrote buyer and suppliers)"
            if args.suppliers == "simulated" else
            "NegMAS check (not a benchmark: independent strategies, our reservation prices)")
    result = {"kind": kind, "suppliers": args.suppliers, "buyer": args.buyer,
              "request": str(args.request), "seeds": f"0..{args.seeds - 1}",
              "scenarios": check(args.request.read_text(encoding="utf-8"), args.seeds, args.suppliers, args.buyer)}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
