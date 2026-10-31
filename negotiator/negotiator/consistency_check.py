"""Self-simulation consistency check: run the negotiator over many seeds and scenarios and count outcomes.

This is NOT a benchmark. This team wrote both the buyer and the simulated suppliers it negotiates against, so the
numbers show that the rules hold and the outcomes are stable, not how the buyer would do against independent
sellers.

    cd negotiator && python3 -m negotiator.consistency_check [--request examples/request.txt] [--seeds 200]
"""

import argparse
import json
import statistics
import time
from pathlib import Path

from .engine import negotiate

SCENARIOS = ("normal", "above_cap", "broken_quote")


def check(text, seeds):
    out = {}
    for scenario in SCENARIOS:
        statuses, savings, rounds, seconds, violations = {}, [], [], [], 0
        for seed in range(seeds):
            t0 = time.perf_counter()
            r = negotiate(text, seed=seed, scenario=scenario)
            seconds.append(time.perf_counter() - t0)
            statuses[r["status"]] = statuses.get(r["status"], 0) + 1
            rounds.append(sum(1 for m in r["transcript"] if m["from"] == "buyer"))
            if r["status"] == "deal":
                q = r["quote"]
                savings.append(100 * (r["winner_opening_unit_price_eur"] - q["unit_price_eur"]) / r["winner_opening_unit_price_eur"])
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
            "buyer_messages_per_run_mean": round(statistics.mean(rounds), 1),
            "ms_per_run_mean": round(1000 * statistics.mean(seconds), 1),
        }
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(prog="negotiator.consistency_check", description=__doc__.split("\n")[0])
    parser.add_argument("--request", type=Path, default=Path("examples/request.txt"))
    parser.add_argument("--seeds", type=int, default=200)
    args = parser.parse_args(argv)
    result = {"kind": "self-simulation consistency check (not a benchmark: same team wrote buyer and suppliers)",
              "request": str(args.request), "seeds": f"0..{args.seeds - 1}",
              "scenarios": check(args.request.read_text(encoding="utf-8"), args.seeds)}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
