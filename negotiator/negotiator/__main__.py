import argparse
import json
import os
import sys
from pathlib import Path

from . import llm
from .engine import SCENARIOS, negotiate


def llm_client():
    """The model client with `NEGOTIATOR_LLM=on`, else None. A misconfigured provider fails every call."""
    if not llm.enabled():
        return None
    try:
        return llm.from_env()
    except (ValueError, OSError) as e:  # names what is wrong, never a value
        print(f"negotiator: LLM unavailable ({e}); free-text replies will count as no bid", file=sys.stderr)
        return llm.Client(llm.Unavailable())


def main(argv=None):
    parser = argparse.ArgumentParser(prog="negotiator", description="Negotiate a first order with three simulated suppliers.")
    parser.add_argument("--request-file", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--scenario", choices=SCENARIOS, default="normal")
    args = parser.parse_args(argv)

    client, paid = llm_client(), os.environ.get("PAID_TASKS_ENABLED") == "true"
    tactician = client is not None and os.environ.get("NEGOTIATOR_TACTICIAN", "").strip().lower() == "on"
    if tactician and paid:
        print("negotiator: the tactician is off while paid tasks are enabled", file=sys.stderr)
        tactician = False
    result = negotiate(args.request_file.read_text(encoding="utf-8"), seed=args.seed, scenario=args.scenario,
                       llm=client, paid=paid, tactician=tactician)
    tmp = args.out.with_name(args.out.name + ".tmp")
    tmp.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, args.out)  # the worker never sees a half-written file


if __name__ == "__main__":
    main()
