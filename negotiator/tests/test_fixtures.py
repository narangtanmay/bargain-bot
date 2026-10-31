import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Checked-in request texts and the statuses every seed must give. Integrations key on `status`, never on prices.
FIXTURES = {
    "request-normal.txt": ("deal", []),
    "request-above-cap.txt": ("no_deal", ["unit_price_within_cap"]),
    "request-broken-quote.txt": ("no_deal", ["confirmation_matches_accepted_sheet", "total_consistent"]),
    "request-real-quotes.txt": ("deal", []),
}


def run(name, tmp_path, seed):
    text = (ROOT / "examples" / name).read_text()
    scenario = next((l.split(":", 1)[1].strip() for l in text.splitlines() if l.lower().startswith("scenario:")), "normal")
    out = tmp_path / "r.json"
    args = [sys.executable, "-m", "negotiator", "--request-file", str(ROOT / "examples" / name), "--out", str(out),
            "--seed", str(seed)]
    if scenario != "normal":
        args += ["--scenario", scenario]
    subprocess.run(args, cwd=ROOT, check=True, capture_output=True)
    return json.loads(out.read_text())


def test_fixture_requests_give_their_expected_status_and_failed_checks(tmp_path):
    for name, (status, must_fail) in FIXTURES.items():
        for seed in (1, 2, 3):
            result = run(name, tmp_path, seed)
            failed = [c["name"] for c in result["checks"] if not c["passed"]]
            assert result["status"] == status, (name, seed)
            assert set(must_fail) <= set(failed), (name, seed, failed)
            assert (result["quote"] is not None) == (status == "deal")
