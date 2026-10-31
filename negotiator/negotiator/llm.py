"""The model layer, kept swappable. The negotiator only ever talks to a `Client`; a `Client` wraps any provider,
which is any object with `model` and `complete(system, user, *, max_tokens, timeout_s) -> (text, usage)`,
where `usage` is `{"input_tokens", "output_tokens"}` and a failure raises.

Off by default. `NEGOTIATOR_LLM=on` turns it on and `NEGOTIATOR_LLM_PROVIDER` picks a provider by name
(default `openai_compatible`). Add one with `register(name, factory)`, where `factory(env)` returns a provider.
Tests pass a `FakeLLM` straight to `Client` and never touch the network.

The model is an untrusted translator and never sets a number. `Client.complete` returns None on any failure, and
callers fail closed on None: the reader gives `no_bid`, the writer keeps its template text.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT_S = 8.0  # per call
BUDGET_S = 30.0  # all calls in one run, well inside the table's 60 s (`engine.TIME_LIMIT_S`)
# Upper bounds for any provider or env override: the table stops at 60 s and may then wait for one last call, which
# keeps a run well inside the worker's 120 s timeout.
MAX_TIMEOUT_S, MAX_BUDGET_S = 30.0, 50.0
MAX_TOKENS = 512
DEFAULT_PROVIDER = "openai_compatible"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class LLMError(Exception):
    """A provider could not give a usable completion. The message never carries a key or a prompt."""


class OpenAICompatible:
    """Any `/chat/completions` endpoint (Z.ai, OpenAI, OpenRouter, a local Ollama or vLLM), stdlib HTTPS only."""

    def __init__(self, base_url, api_key, model, extra=None, min_tokens=0):
        parts = urllib.parse.urlsplit(base_url)
        if parts.scheme != "https" and not (parts.scheme == "http" and parts.hostname in LOCAL_HOSTS):
            raise ValueError("the model base URL must be https (plain http only for localhost)")
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self._key = api_key
        self.extra = dict(extra or {})  # provider-specific request fields
        self.min_tokens = min_tokens  # a reasoning model spends its output budget on thinking before it answers

    def __repr__(self):
        return f"OpenAICompatible(url={self.url!r}, model={self.model!r})"

    def complete(self, system, user, *, max_tokens, timeout_s):
        body = {"model": self.model, "max_tokens": max(max_tokens, self.min_tokens), "temperature": 0, **self.extra,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                data = json.load(resp)
        except urllib.error.HTTPError as e:
            raise LLMError(f"HTTP {e.code}") from None
        except (OSError, ValueError) as e:  # URLError, timeouts and bad JSON; the cause may quote the request
            raise LLMError(type(e).__name__) from None
        try:
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
            tokens = {"input_tokens": int(usage.get("prompt_tokens") or 0),
                      "output_tokens": int(usage.get("completion_tokens") or 0),  # reasoning included
                      "reasoning_tokens": int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)}
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            raise LLMError("unexpected response shape") from None
        if not isinstance(text, str):
            raise LLMError("unexpected response shape")
        return text, tokens


class FakeLLM:
    """Scripted provider for tests and offline runs. Each reply is a string, an exception to raise, or a callable
    `(system, user) -> str`. Every prompt is kept in `prompts`. With no reply left, it raises."""

    model = "fake"

    def __init__(self, replies=()):
        self.replies = list(replies)
        self.prompts = []

    def complete(self, system, user, *, max_tokens, timeout_s):
        self.prompts.append((system, user))
        if not self.replies:
            raise LLMError("no scripted reply left")
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        text = reply(system, user) if callable(reply) else reply
        return text, {"input_tokens": len(f"{system} {user}".split()), "output_tokens": len(str(text).split())}


class Unavailable:
    """Stands in for a provider that could not be set up: every call fails, so callers fail closed."""

    model = None

    def complete(self, system, user, *, max_tokens, timeout_s):
        raise LLMError("no provider")


class Client:
    """What the negotiator calls. Enforces the per-call timeout and the run budget, counts calls, failures, tokens
    and seconds, and turns every failure into None."""

    def __init__(self, provider, *, timeout_s=TIMEOUT_S, budget_s=BUDGET_S):
        self.provider = provider
        self.timeout_s, self.budget_s = timeout_s, budget_s
        self.calls = self.failures = self.input_tokens = self.output_tokens = self.reasoning_tokens = 0
        self.seconds = 0.0
        self.budget_skips = 0

    def complete(self, system, user, *, max_tokens=MAX_TOKENS):
        """The model's text, or None. Never raises."""
        timeout_s = min(self.timeout_s, self.budget_s - self.seconds)
        if timeout_s <= 0:
            self.budget_skips += 1
            return None
        self.calls += 1
        start = time.monotonic()
        try:
            text, usage = self.provider.complete(system, user, max_tokens=max_tokens, timeout_s=timeout_s)
            self.input_tokens += int(usage.get("input_tokens", 0))
            self.output_tokens += int(usage.get("output_tokens", 0))
            self.reasoning_tokens += int(usage.get("reasoning_tokens", 0))
        except Exception:  # any provider bug fails closed, like a supplier's malformed reply
            text = None
        elapsed = time.monotonic() - start
        self.seconds += elapsed
        if not isinstance(text, str) or elapsed > timeout_s:  # a late answer counts as a timeout
            self.failures += 1
            return None
        return text

    def usage(self):
        return {"calls": self.calls, "failures": self.failures, "budget_skips": self.budget_skips, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens, "reasoning_tokens": self.reasoning_tokens,
                "seconds": round(self.seconds, 3),
                "model": getattr(self.provider, "model", None)}


def _need(env, *names):
    missing = [n for n in names if not env.get(n, "").strip()]
    if missing:
        raise ValueError("missing " + ", ".join(missing))
    return [env[n].strip() for n in names]


def _openai_compatible(env):
    base_url, key, model = _need(env, "ZAI_BASE_URL", "ZAI_API_KEY", "ZAI_MODEL")
    return OpenAICompatible(base_url, key, model)


def _deepseek(env):
    """DeepSeek's OpenAI-format API, in its default thinking mode (effort `high`, or `DEEPSEEK_REASONING_EFFORT`).
    Its output budget counts the thinking, so a short answer still gets `DEEPSEEK_MAX_TOKENS` (default 4096), and
    it gets more time per call than a plain completion. A cut-off answer has no JSON, so callers fail closed."""
    (key,) = _need(env, "DEEPSEEK_API_KEY")
    base_url = env.get("DEEPSEEK_BASE_URL", "").strip() or "https://api.deepseek.com"
    model = env.get("DEEPSEEK_MODEL", "").strip() or "deepseek-flash"
    effort = env.get("DEEPSEEK_REASONING_EFFORT", "").strip().lower()
    if effort and effort not in ("none", "low", "high", "max"):
        raise ValueError("DEEPSEEK_REASONING_EFFORT must be none, low, high or max")
    provider = OpenAICompatible(base_url, key, model, extra={"reasoning_effort": effort} if effort else None,
                                min_tokens=_whole(env, "DEEPSEEK_MAX_TOKENS", 4096))
    provider.timeout_s, provider.budget_s = 25.0, MAX_BUDGET_S
    return provider


def _whole(env, name, default):
    raw = env.get(name, "").strip()
    if not raw:
        return default
    if not raw.isdigit() or int(raw) <= 0:
        raise ValueError(f"{name} must be a positive whole number")
    return int(raw)


def _seconds(env, name, default, limit):
    raw = env.get(name, "").strip()
    try:
        value = float(raw) if raw else default
    except ValueError:
        raise ValueError(f"{name} must be a number of seconds") from None
    if not 0 < value <= limit:
        raise ValueError(f"{name} must be above 0 and at most {limit:g}")
    return value


def _fake(env):
    """Offline runs without a key: `NEGOTIATOR_LLM_FAKE_REPLIES` names a JSON file with a list of reply strings."""
    (path,) = _need(env, "NEGOTIATOR_LLM_FAKE_REPLIES")
    with open(path, encoding="utf-8") as f:
        replies = json.load(f)
    if not isinstance(replies, list) or not all(isinstance(r, str) for r in replies):
        raise ValueError("NEGOTIATOR_LLM_FAKE_REPLIES must name a JSON list of strings")
    return FakeLLM(replies)


PROVIDERS = {"openai_compatible": _openai_compatible, "deepseek": _deepseek, "fake": _fake}


def register(name, factory):
    """Make a provider selectable with `NEGOTIATOR_LLM_PROVIDER=<name>`. `factory(env)` returns the provider."""
    PROVIDERS[name] = factory


def enabled(env=None):
    env = os.environ if env is None else env
    return env.get("NEGOTIATOR_LLM", "").strip().lower() == "on"


def from_env(env=None):
    """A Client for the configured provider, or None when the flag is off. A misconfigured provider raises
    ValueError naming what is wrong, never a value."""
    env = os.environ if env is None else env
    if not enabled(env):
        return None
    name = env.get("NEGOTIATOR_LLM_PROVIDER", "").strip() or DEFAULT_PROVIDER
    if name not in PROVIDERS:
        raise ValueError(f"unknown NEGOTIATOR_LLM_PROVIDER {name!r}; known: {', '.join(sorted(PROVIDERS))}")
    provider = PROVIDERS[name](env)
    timeout = _seconds(env, "NEGOTIATOR_LLM_TIMEOUT_S", getattr(provider, "timeout_s", TIMEOUT_S), MAX_TIMEOUT_S)
    budget = _seconds(env, "NEGOTIATOR_LLM_BUDGET_S", getattr(provider, "budget_s", BUDGET_S), MAX_BUDGET_S)
    return Client(provider, timeout_s=timeout, budget_s=budget)
