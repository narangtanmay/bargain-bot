"""Read-only Vast.ai price-selection benchmark: one H100 SXM 80GB on-demand GPU.

This measures a price-SELECTION opportunity in public listings: how much cheaper the cheapest offer that meets
fixed requirements is than the median eligible offer, at the same moment. It is not a negotiation: no offer is
made, bid, rented or paid for, and nothing here is a negotiated discount.

    python3 benchmark.py fetch [--snapshots 3] [--interval-s 120]   # public GET only, no API key
    python3 benchmark.py analyze                                     # writes offers.csv and results.json

Requirements are fixed in PROFILES before any ranking. Prices are USD per hour as listed (`dph_total`: the GPU rate
plus a small default-disk amount), kept in USD. Extra storage and transfer are reported per offer but not added, so
claims are limited to the listed hourly rate.
"""

import argparse
import csv
import json
import statistics
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SNAPSHOTS = HERE / "snapshots"
ENDPOINT = "https://console.vast.ai/api/v0/bundles/"
QUERY = {"gpu_name": {"eq": "H100 SXM"}, "num_gpus": {"eq": 1}, "rentable": {"eq": True}, "type": "on-demand"}
STRICT = {  # declared before ranking; an offer must meet all of them to be eligible
    "gpu_name": "H100 SXM",
    "num_gpus": 1,
    "min_gpu_ram_mb": 80000,
    "on_demand_only": True,
    "verified_host": True,
    "min_reliability": 0.98,
    "min_cpu_cores_effective": 16,
    "min_cpu_ram_mb": 64000,
    "min_disk_gb": 200,
    "region": "any",
}
# Declared with STRICT, reported side by side: the same set without the verified-host rule, to show how much that
# one rule drives the result. Not a choice made after looking at prices.
PROFILES = {"strict": STRICT, "without_verified_host": {**STRICT, "verified_host": False}}
REDACT = ("public_ipaddr",)  # third-party host addresses are not stored
FIELDS = ("id", "machine_id", "host_id", "gpu_name", "num_gpus", "gpu_ram", "dph_total", "dph_base", "storage_cost",
          "internet_up_cost_per_tb", "internet_down_cost_per_tb", "reliability", "verification", "geolocation",
          "cpu_cores_effective", "cpu_ram", "disk_space", "is_bid", "rentable", "rented")


def fetch_once():
    url = ENDPOINT + "?" + urllib.parse.urlencode({"q": json.dumps(QUERY)})
    collected = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record = {"collected_utc": collected, "method": "GET", "url": url, "query": QUERY}
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "tum-negotiation-benchmark"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            record["http_status"] = resp.status
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # record the actual failure instead of inventing data
        record["http_status"], record["error"] = getattr(e, "code", None), repr(e)
        return record
    offers = body.get("offers", [])
    record["truncated"] = body.get("truncated")
    record["offers"] = [{k: v for k, v in o.items() if k not in REDACT} for o in offers]
    return record


def fetch(n, interval):
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        if i:
            time.sleep(interval)
        record = fetch_once()
        name = record["collected_utc"].replace(":", "").replace("+0000", "Z")
        (SNAPSHOTS / f"{name}.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
        print(record["collected_utc"], record.get("http_status"), len(record.get("offers", [])), "offers",
              record.get("error", ""), file=sys.stderr)


def exclusion(o, r):
    """(rule, detail) of the first requirement this offer fails, or None when it is eligible."""
    checks = [
        ("gpu_name", o.get("gpu_name") == r["gpu_name"], f"gpu_name {o.get('gpu_name')}"),
        ("num_gpus", o.get("num_gpus") == r["num_gpus"], f"num_gpus {o.get('num_gpus')}"),
        ("gpu_ram", (o.get("gpu_ram") or 0) >= r["min_gpu_ram_mb"], f"gpu_ram {o.get('gpu_ram')} MB"),
        ("interruptible", not o.get("is_bid"), "interruptible (bid) offer"),
        ("verification", not r["verified_host"] or o.get("verification") == "verified", f"host verification {o.get('verification')}"),
        ("reliability", (o.get("reliability") or 0) >= r["min_reliability"], f"reliability {o.get('reliability'):.4f}"),
        ("cpu_cores", (o.get("cpu_cores_effective") or 0) >= r["min_cpu_cores_effective"], f"cpu_cores_effective {o.get('cpu_cores_effective')}"),
        ("cpu_ram", (o.get("cpu_ram") or 0) >= r["min_cpu_ram_mb"], f"cpu_ram {o.get('cpu_ram')} MB"),
        ("disk", (o.get("disk_space") or 0) >= r["min_disk_gb"], f"disk_space {o.get('disk_space')} GB"),
    ]
    return next(((rule, why) for rule, ok, why in checks if not ok), None)


def summarize(snap, profile):
    if "offers" not in snap:
        return {"collected_utc": snap["collected_utc"], "http_status": snap.get("http_status"), "error": snap.get("error")}
    eligible, excluded = [], {}
    for o in snap["offers"]:
        fail = exclusion(o, profile)
        if fail:
            excluded[fail[0]] = excluded.get(fail[0], 0) + 1
        else:
            eligible.append(o)
    entry = {"collected_utc": snap["collected_utc"], "http_status": snap["http_status"], "truncated": snap.get("truncated"),
             "offers": len(snap["offers"]), "unique_machines": len({o["machine_id"] for o in snap["offers"]}),
             "unique_hosts": len({o["host_id"] for o in snap["offers"]}), "eligible_offers": len(eligible),
             "eligible_unique_hosts": len({o["host_id"] for o in eligible}), "excluded_by_first_failed_rule": excluded}
    if eligible:
        prices = sorted(o["dph_total"] for o in eligible)
        hosts = {o["host_id"] for o in eligible}
        host_best = sorted(min(o["dph_total"] for o in eligible if o["host_id"] == h) for h in hosts)
        cheapest = min(eligible, key=lambda o: o["dph_total"])
        med, med_h = statistics.median(prices), statistics.median(host_best)
        entry.update({
            "cheapest_usd_per_hour": round(prices[0], 4),
            "cheapest_offer": {k: cheapest.get(k) for k in ("id", "machine_id", "host_id", "geolocation", "reliability")},
            "median_eligible_offer_usd_per_hour": round(med, 4),
            "median_of_host_cheapest_usd_per_hour": round(med_h, 4),
            "max_eligible_usd_per_hour": round(prices[-1], 4),
            "cheapest_vs_median_offer_pct": round(100 * (med - prices[0]) / med, 1),
            "cheapest_vs_median_host_pct": round(100 * (med_h - prices[0]) / med_h, 1),
            "small_sample_warning": len(hosts) < 5,
        })
    return entry


def analyze():
    snaps = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(SNAPSHOTS.glob("*.json"))]
    rows = []
    for s in snaps:
        for o in s.get("offers", []):
            row = {"collected_utc": s["collected_utc"], **{k: o.get(k) for k in FIELDS}}
            for name, profile in PROFILES.items():
                fail = exclusion(o, profile)
                row[f"eligible_{name}"], row[f"excluded_{name}"] = fail is None, fail[1] if fail else ""
            rows.append(row)
    with open(HERE / "offers.csv", "w", newline="", encoding="utf-8") as f:
        names = [x for n in PROFILES for x in (f"eligible_{n}", f"excluded_{n}")]
        writer = csv.DictWriter(f, fieldnames=["collected_utc", *FIELDS, *names])
        writer.writeheader()
        writer.writerows(rows)
    all_offers = [o for s in snaps for o in s.get("offers", [])]
    result = {
        "kind": "read-only price-selection benchmark (public listings; no offers, bids, rentals or payments)",
        "currency": "USD per hour, listed dph_total; storage and transfer not included",
        "profiles": PROFILES,
        "snapshots": {name: [summarize(s, p) for s in snaps] for name, p in PROFILES.items()},
        "across_snapshots": {"listings_seen": len(all_offers), "unique_offer_ids": len({o["id"] for o in all_offers}),
                             "unique_machines": len({o["machine_id"] for o in all_offers}),
                             "unique_hosts": len({o["host_id"] for o in all_offers})},
    }
    (HERE / "results.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=1))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--snapshots", type=int, default=3)
    f.add_argument("--interval-s", type=int, default=120)
    sub.add_parser("analyze")
    a = p.parse_args(argv)
    fetch(a.snapshots, a.interval_s) if a.cmd == "fetch" else analyze()


if __name__ == "__main__":
    main()
