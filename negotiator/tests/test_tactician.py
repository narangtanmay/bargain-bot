import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from negotiator import llm
from negotiator.engine import negotiate
from negotiator.llm import Client, FakeLLM, LLMError
from negotiator.tactician import SYSTEM

ROOT = Path(__file__).resolve().parent.parent
TEXT = (ROOT / "examples" / "request.txt").read_text()
CAP = 4.80


class Always:
    """A fake model that always picks one option ID when it is listed, else the first option."""

    model = "always"

    def __init__(self, pick):
        self.pick, self.prompts = pick, []

    def complete(self, system, user, *, max_tokens, timeout_s):
        self.prompts.append((system, user))
        ids = re.findall(r"^- (\w+):", user, re.M)
        return json.dumps({"option": self.pick if self.pick in ids else ids[0], "reason": "test"}), \
            {"input_tokens": 1, "output_tokens": 1}


def run(provider, seed=1, **kw):
    return negotiate(TEXT, seed=seed, llm=Client(provider), tactician=True, **kw)


def offers(result):
    return [m["unit_price_eur"] for m in result["transcript"] if m["from"] == "buyer" and m["unit_price_eur"] is not None]


def test_choosing_e0_changes_nothing_but_the_added_fields():
    for seed in (1, 2, 3):
        base, result = negotiate(TEXT, seed=seed), run(Always("E0"), seed)
        assert result["log_hash"] == base["log_hash"] and result["transcript"] == base["transcript"]
        assert result["quote"] == base["quote"] and result["checks"] == base["checks"]
        assert result["tactician"] and all(p["chosen"] == "E0" and p["fallback"] is None for p in result["tactician"])


@pytest.mark.parametrize("reply", ["nonsense", "{broken", json.dumps({"option": "EUR 3.00"}),
                                   json.dumps({"option": "step99"}), json.dumps(["E0"]), LLMError("down"),
                                   TimeoutError()])
def test_invalid_answers_and_failures_send_the_engines_move(reply):
    base, result = negotiate(TEXT, seed=1), run(FakeLLM([reply] * 50))
    assert result["log_hash"] == base["log_hash"] and result["quote"] == base["quote"]
    assert all(p["chosen"] == "E0" and p["fallback"] for p in result["tactician"])


@pytest.mark.parametrize("pick", ["anchor75", "anchor85", "hold", "step10", "step50", "accept"])
def test_whatever_it_picks_every_price_is_code_set_and_every_rule_holds(pick):
    for seed in range(1, 11):
        result = run(Always(pick), seed)
        assert result["status"] == "deal", (pick, seed)
        assert all(c["passed"] for c in result["checks"])
        assert result["quote"]["unit_price_eur"] <= CAP
        assert result["quote"]["unit_price_eur"] < result["winner_opening_unit_price_eur"]
        assert all(p <= CAP for p in offers(result))


def test_a_picked_price_is_the_price_sent():
    result = run(Always("step10"), seed=1)
    picked = [p for p in result["tactician"] if p["chosen"] == "step10"]
    assert picked
    sent = offers(result)
    for p in picked:
        assert p["options"]["step10"] in sent


def test_only_ordinary_offers_go_to_the_model():
    provider = Always("E0")
    result = run(provider, seed=3)
    asked = len(provider.prompts)
    assert asked == len(result["tactician"]) == result["llm"]["calls"]
    rfqs, accepts = 3, 1
    buyer_lines = [m for m in result["transcript"] if m["from"] == "buyer"]
    last_calls = [m for m in buyer_lines if "please send it now" in m["text"]]
    closes = [m for m in buyer_lines if "will not proceed" in m["text"]]
    assert asked == len(buyer_lines) - rfqs - accepts - len(last_calls) - len(closes)


def test_the_prompt_carries_no_cap_and_the_model_writes_no_number():
    provider = Always("E0")
    run(provider, seed=2)
    for system, user in provider.prompts:
        assert system == SYSTEM
        assert not re.search(r"\b(cap|max|budget|limit|ceiling)\b", (system + user).lower())


def test_summary_says_what_the_model_did():
    summary = run(Always("hold"), seed=1)["summary_markdown"]
    assert "## Tactician" in summary and "wrote no number" in summary
    assert "an LLM chose among code-priced offers but set no price" in summary
    assert "no LLM sets or reads prices" not in summary


def test_without_the_tactician_flag_the_buyer_is_the_engine():
    result = negotiate(TEXT, seed=1, llm=Client(Always("hold")))
    assert "tactician" not in result and result["llm"]["calls"] == 0


def _cli(tmp_path, **env_extra):
    replies = tmp_path / "replies.json"
    replies.write_text(json.dumps([json.dumps({"option": "hold", "reason": "x"})] * 50))
    out = tmp_path / "out.json"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("NEGOTIATOR_", "PAID_", "DEEPSEEK_"))}
    env.update(NEGOTIATOR_LLM="on", NEGOTIATOR_LLM_PROVIDER="fake", NEGOTIATOR_LLM_FAKE_REPLIES=str(replies),
               NEGOTIATOR_TACTICIAN="on", **env_extra)
    proc = subprocess.run([sys.executable, "-m", "negotiator", "--request-file", str(ROOT / "examples" / "request.txt"),
                           "--out", str(out)], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    return json.loads(out.read_text()), proc.stderr


def test_cli_runs_the_tactician_with_its_flag(tmp_path):
    result, _ = _cli(tmp_path)
    assert result["status"] == "deal" and any(p["chosen"] == "hold" for p in result["tactician"])


def test_cli_turns_the_tactician_off_while_paid_tasks_are_enabled(tmp_path):
    result, stderr = _cli(tmp_path, PAID_TASKS_ENABLED="true")
    assert "tactician" not in result and "tactician is off while paid tasks are enabled" in stderr


def test_deepseek_provider_keeps_thinking_on_with_room_and_time_to_think(monkeypatch):
    env = {"NEGOTIATOR_LLM": "on", "NEGOTIATOR_LLM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "sk-x"}
    client = llm.from_env(env)
    provider = client.provider
    assert provider.url == "https://api.deepseek.com/chat/completions" and provider.model == "deepseek-flash"
    assert (client.timeout_s, client.budget_s) == (25.0, 50.0)
    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "{}", "reasoning_content": "..."}}],
                               "usage": {"prompt_tokens": 50, "completion_tokens": 900,
                                         "completion_tokens_details": {"reasoning_tokens": 880}}}).encode()

    def fake_urlopen(req, timeout):
        seen.clear()
        seen.update(json.loads(req.data))
        return Resp()

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    assert client.complete("s", "u", max_tokens=120) == "{}"
    assert "thinking" not in seen and "reasoning_effort" not in seen  # DeepSeek's default: thinking, effort high
    assert seen["max_tokens"] == 4096 and seen["model"] == "deepseek-flash"
    assert client.usage()["reasoning_tokens"] == 880 and client.usage()["output_tokens"] == 900

    client = llm.from_env({**env, "DEEPSEEK_REASONING_EFFORT": "low", "DEEPSEEK_MAX_TOKENS": "2000",
                           "NEGOTIATOR_LLM_TIMEOUT_S": "12"})
    client.complete("s", "u", max_tokens=120)
    assert seen["reasoning_effort"] == "low" and seen["max_tokens"] == 2000 and client.timeout_s == 12.0
    for bad in ({"DEEPSEEK_REASONING_EFFORT": "huge"}, {"DEEPSEEK_MAX_TOKENS": "-1"},
                {"NEGOTIATOR_LLM_TIMEOUT_S": "90"}, {"NEGOTIATOR_LLM_BUDGET_S": "500"}):
        with pytest.raises(ValueError):
            llm.from_env({**env, **bad})
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        llm.from_env({"NEGOTIATOR_LLM": "on", "NEGOTIATOR_LLM_PROVIDER": "deepseek"})


def test_the_buyer_remembers_the_price_actually_sent():
    import random

    from negotiator import table
    from negotiator.buyer import Buyer
    from negotiator.request import parse_request
    from negotiator.suppliers import PERSONAS, Supplier
    from negotiator.tactician import Tactician

    request, _ = parse_request(TEXT)
    rng = random.Random(1)
    suppliers = {p.sid: Supplier(p, request, rng, "normal", 1) for p in PERSONAS}
    tactician = Tactician(Buyer(request), Client(Always("step10")))
    out = table.run(tactician, suppliers, request)
    for sid, side in tactician.buyer.sides.items():
        sent = [m["terms"]["unit_price"] for m in out["threads"][sid] if m.get("type") == "send"]
        assert side.ours == sent, sid


def test_summary_counts_only_real_call_failures_and_reports_budget_skips():
    client = Client(FakeLLM(["ok", LLMError("down")]))
    client.complete("s", "u")
    client.complete("s", "u")
    client.seconds = client.budget_s
    result = negotiate(TEXT, seed=1, llm=client, tactician=True)
    assert result["llm"]["budget_skips"] > 0
    assert "2 calls (1 failed;" in result["summary_markdown"]
    assert f"{result['llm']['budget_skips']} budget skips" in result["summary_markdown"]
