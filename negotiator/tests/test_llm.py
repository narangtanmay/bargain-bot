import io
import json
import time
import urllib.error

import pytest

from negotiator import llm
from negotiator.llm import Client, FakeLLM, LLMError, OpenAICompatible

KEY = "sk-test-secret-123"
ZAI = {"NEGOTIATOR_LLM": "on", "ZAI_BASE_URL": "https://api.example.test/v1", "ZAI_API_KEY": KEY, "ZAI_MODEL": "m-1"}


def test_flag_off_or_unset_gives_no_client():
    assert llm.from_env({}) is None
    assert llm.from_env({"NEGOTIATOR_LLM": "off", "ZAI_API_KEY": KEY}) is None
    assert llm.from_env({"NEGOTIATOR_LLM": "yes"}) is None  # only "on" turns it on


def test_default_provider_is_openai_compatible_from_the_zai_slots():
    client = llm.from_env(ZAI)
    assert isinstance(client.provider, OpenAICompatible)
    assert client.provider.url == "https://api.example.test/v1/chat/completions"
    assert client.usage()["model"] == "m-1"
    assert KEY not in repr(client.provider)


def test_missing_settings_name_the_variable_never_a_value():
    with pytest.raises(ValueError) as e:
        llm.from_env({**ZAI, "ZAI_MODEL": ""})
    assert "ZAI_MODEL" in str(e.value) and KEY not in str(e.value)
    with pytest.raises(ValueError, match="unknown NEGOTIATOR_LLM_PROVIDER"):
        llm.from_env({**ZAI, "NEGOTIATOR_LLM_PROVIDER": "nope"})


def test_key_is_never_sent_over_plain_http_except_to_localhost():
    with pytest.raises(ValueError, match="https"):
        OpenAICompatible("http://api.example.test/v1", KEY, "m")
    assert OpenAICompatible("http://localhost:11434/v1", KEY, "m").url.startswith("http://localhost")


def test_a_registered_provider_is_selectable_by_name(monkeypatch):
    monkeypatch.setitem(llm.PROVIDERS, "scripted", lambda env: FakeLLM([env["REPLY"]]))
    client = llm.from_env({"NEGOTIATOR_LLM": "on", "NEGOTIATOR_LLM_PROVIDER": "scripted", "REPLY": "hello"})
    assert client.complete("sys", "user") == "hello"


def test_fake_provider_from_env_reads_scripted_replies(tmp_path):
    replies = tmp_path / "replies.json"
    replies.write_text(json.dumps(["one", "two"]))
    client = llm.from_env({"NEGOTIATOR_LLM": "on", "NEGOTIATOR_LLM_PROVIDER": "fake",
                           "NEGOTIATOR_LLM_FAKE_REPLIES": str(replies)})
    assert [client.complete("s", "u") for _ in range(3)] == ["one", "two", None]
    replies.write_text(json.dumps({"not": "a list"}))
    with pytest.raises(ValueError):
        llm.from_env({"NEGOTIATOR_LLM": "on", "NEGOTIATOR_LLM_PROVIDER": "fake",
                      "NEGOTIATOR_LLM_FAKE_REPLIES": str(replies)})


def test_client_counts_calls_and_tokens():
    fake = FakeLLM(["a b c", lambda system, user: user.upper()])
    client = Client(fake)
    assert client.complete("sys", "one two") == "a b c"
    assert client.complete("sys", "x") == "X"
    usage = client.usage()
    assert (usage["calls"], usage["failures"], usage["model"]) == (2, 0, "fake")
    assert usage["input_tokens"] == 5 and usage["output_tokens"] == 4
    assert fake.prompts == [("sys", "one two"), ("sys", "x")]


@pytest.mark.parametrize("reply", [LLMError("down"), TimeoutError(), RuntimeError("provider bug"), lambda s, u: 42])
def test_client_fails_closed_on_any_provider_failure(reply):
    client = Client(FakeLLM([reply]))
    assert client.complete("s", "u") is None
    assert client.usage()["failures"] == 1


def test_a_late_answer_counts_as_a_timeout():
    def slow(system, user):
        time.sleep(0.05)
        return "too late"
    client = Client(FakeLLM([slow]), timeout_s=0.01)
    assert client.complete("s", "u") is None and client.usage()["failures"] == 1


def test_an_exhausted_budget_stops_calling_the_provider():
    fake = FakeLLM(["never"])
    client = Client(fake, budget_s=0.0)
    assert client.complete("s", "u") is None
    assert fake.prompts == [] and client.usage()["calls"] == 0


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_openai_compatible_sends_bearer_key_and_parses_the_reply(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout):
        seen.update(url=req.full_url, auth=req.get_header("Authorization"), body=json.loads(req.data), timeout=timeout)
        return _Resp(json.dumps({"choices": [{"message": {"content": "hi"}}],
                                 "usage": {"prompt_tokens": 7, "completion_tokens": 2}}).encode())

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    text, usage = OpenAICompatible("https://api.example.test/v1/", KEY, "m-1").complete(
        "sys", "user", max_tokens=64, timeout_s=8)
    assert (text, usage) == ("hi", {"input_tokens": 7, "output_tokens": 2, "reasoning_tokens": 0})
    assert seen["url"] == "https://api.example.test/v1/chat/completions" and seen["auth"] == f"Bearer {KEY}"
    assert seen["body"]["model"] == "m-1" and seen["body"]["max_tokens"] == 64 and seen["timeout"] == 8
    assert [m["role"] for m in seen["body"]["messages"]] == ["system", "user"]


@pytest.mark.parametrize("outcome", [
    urllib.error.HTTPError("https://x", 401, "unauthorized", {}, None),
    urllib.error.URLError("unreachable"),
    TimeoutError(),
    b"not json",
    json.dumps({"choices": []}).encode(),
    json.dumps({"choices": [{"message": {"content": None}}]}).encode(),
])
def test_openai_compatible_errors_become_llm_errors_without_the_key(monkeypatch, outcome):
    def fake_urlopen(req, timeout):
        if isinstance(outcome, BaseException):
            raise outcome
        return _Resp(outcome)

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(LLMError) as e:
        OpenAICompatible("https://api.example.test/v1", KEY, "m").complete("s", "u", max_tokens=8, timeout_s=1)
    assert KEY not in str(e.value) and e.value.__cause__ is None


def test_budget_skips_are_not_counted_as_failed_api_calls():
    provider = FakeLLM(["ok", LLMError("down")])
    client = Client(provider)
    assert client.complete("s", "u") == "ok"
    assert client.complete("s", "u") is None
    client.seconds = client.budget_s
    assert client.complete("s", "u") is None
    assert client.complete("s", "u") is None
    usage = client.usage()
    assert (usage["calls"], usage["failures"], usage["budget_skips"]) == (2, 1, 2)
    assert len(provider.prompts) == 2
