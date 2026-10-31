import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from negotiator.engine import negotiate
from negotiator.llm import Client, Unavailable
from prose_oracle import Oracle

ROOT = Path(__file__).resolve().parent.parent
TEXT = (ROOT / "examples" / "request.txt").read_text()
ADDED = ("supplier_channels", "llm")


def run(channel, seed=1, scenario="normal", oracle=None, text=TEXT, **kw):
    client = Client(oracle or Oracle())
    return negotiate(f"{text}\nsupplier_channel: {channel}\n", seed=seed, scenario=scenario, llm=client, **kw), client


def check(result, name):
    return next(c for c in result["checks"] if c["name"] == name)


@pytest.mark.parametrize("channel", ["free_text", "mixed"])
def test_free_text_suppliers_read_correctly_reach_the_same_deal_as_protocol_suppliers(channel):
    for seed in range(1, 6):
        base = negotiate(TEXT, seed=seed)
        result, client = run(channel, seed)
        assert result["status"] == base["status"] == "deal", seed
        for key in ("supplier", "unit_price_eur", "quantity", "delivery_days", "payment_terms_days"):
            assert result["quote"][key] == base["quote"][key], (seed, key)
        assert result["savings_eur"] == base["savings_eur"]
        assert result["llm"]["calls"] > 0 and result["llm"]["failures"] == 0
        assert not any(m.get("read_error") for m in result["transcript"])


def test_a_free_text_winner_has_no_signature_and_says_so():
    result, _ = run("free_text", seed=1)
    assert result["status"] == "deal" and result["quote"]["confirmation"]["channel"] == "free_text"
    assert "signature" not in result["quote"]["confirmation"]
    assert check(result, "confirmation_signature_valid") == {
        "name": "confirmation_signature_valid", "passed": True,
        "detail": "not applicable: free-text supplier, identity not verified"}
    assert result["public_keys"] == {}
    assert set(result["supplier_channels"].values()) == {"free_text"}
    summary = result["summary_markdown"]
    assert "## LLM adapter" in summary and "identity is not verified" in summary and "set no price" in summary
    assert "no LLM sets or reads prices" not in summary


def test_mixed_keeps_signatures_for_protocol_suppliers():
    result, _ = run("mixed", seed=2)  # Supplier B wins on protocol
    assert result["quote"]["supplier"] == "Supplier B"
    assert check(result, "confirmation_signature_valid")["detail"] == "Ed25519 signature verifies"
    assert result["supplier_channels"] == {"Supplier A": "free_text", "Supplier B": "protocol", "Supplier C": "protocol"}
    assert set(result["public_keys"]) == {"Supplier B", "Supplier C"}


def test_free_text_runs_keep_the_accept_gate_and_the_checker():
    for seed in (1, 2, 3):
        result, _ = run("free_text", seed, scenario="above_cap")
        assert result["status"] == "no_deal" and not check(result, "unit_price_within_cap")["passed"]
        result, _ = run("free_text", seed, scenario="broken_quote")
        assert result["status"] == "no_deal" and not check(result, "total_consistent")["passed"], seed
        result, _ = run("free_text", seed)
        assert result["quote"]["unit_price_eur"] <= 4.80  # within the cap
        assert result["quote"]["unit_price_eur"] < result["winner_opening_unit_price_eur"]  # strictly below opening


@pytest.mark.parametrize("tamper", [lambda body: body.replace("EUR", "EUR 3.10 or", 1),
                                    lambda body: body.replace("per unit", "per unit (EUR 0.99 for you)", 1),
                                    lambda body: "Our budget is tight. " + body])
def test_a_model_that_rewrites_the_price_cannot_change_what_the_buyer_offers(tamper):
    base = negotiate(TEXT, seed=1)
    result, _ = run("free_text", seed=1, oracle=Oracle(rewrite=tamper))
    assert result["quote"]["unit_price_eur"] == base["quote"]["unit_price_eur"]
    offers = [m for m in result["transcript"] if m["from"] == "buyer" and m["unit_price_eur"] is not None]
    assert offers and all("3.10" not in m["text"] and "0.99" not in m["text"] and "budget" not in m["text"]
                          for m in offers)
    assert [m["unit_price_eur"] for m in offers] == [m["unit_price_eur"] for m in base["transcript"]
                                                     if m["from"] == "buyer" and m["unit_price_eur"] is not None]


def test_a_dead_model_means_no_bid_from_free_text_suppliers_never_a_deal():
    client = Client(Unavailable())
    result = negotiate(TEXT + "\nsupplier_channel: free_text\n", seed=1, llm=client)
    assert result["status"] == "no_deal" and result["quote"] is None and result["checks"] == []
    assert "No supplier returned a usable offer" in result["summary_markdown"]
    assert all(m["read_error"] for m in result["transcript"] if m["from"] == "supplier")
    result = negotiate(TEXT + "\nsupplier_channel: mixed\n", seed=1, llm=Client(Unavailable()))
    assert result["status"] == "deal" and result["quote"]["supplier"] != "Supplier A"


def test_transcript_shows_what_was_sent_and_what_the_supplier_wrote():
    result, client = run("free_text", seed=1)
    sent = [p[1] for p in client.provider.prompts]
    lines = result["transcript"]
    supplier_lines = [m for m in lines if m["from"] == "supplier"]
    assert all("read_error" in m for m in supplier_lines)
    assert any(m["text"].startswith("Many thanks for your quote.") for m in lines if m["from"] == "buyer")
    assert any(m["text"] in p for m in supplier_lines for p in sent)


def test_no_supplier_internals_reach_the_result_or_any_prompt():
    for channel in ("free_text", "mixed"):
        for scenario in ("normal", "above_cap", "broken_quote"):
            result, client = run(channel, seed=3, scenario=scenario)
            result.pop("summary_markdown")
            prompts = json.dumps(client.provider.prompts)
            dumped = json.dumps(result) + prompts
            for secret in ("floor", "markup", "scenario", "above_cap", "broken_quote", "private"):
                assert secret not in dumped, (channel, scenario, secret)
            assert "cap" not in prompts.lower()
            if scenario == "normal":  # under above_cap the buyer's own counter reaches the cap, as it does on protocol
                assert "4.80" not in prompts


def test_flag_on_with_protocol_suppliers_only_adds_the_new_fields():
    for seed in (1, 2, 3):
        base = negotiate(TEXT, seed=seed)
        result, client = run("protocol", seed)
        assert {k: v for k, v in result.items() if k not in ADDED} == base
        assert result["llm"]["calls"] == 0 and set(result["supplier_channels"].values()) == {"protocol"}
        assert negotiate(TEXT, seed=seed, llm=Client(Oracle()))["supplier_channels"] == result["supplier_channels"]


def test_paid_tasks_or_a_bad_channel_line_refuse_free_text():
    result, _ = run("free_text", paid=True)
    assert result["status"] == "invalid_request"
    assert any("demo only" in e for e in result["errors"]) and "llm" in result
    assert run("protocol", paid=True)[0]["status"] == "deal"
    assert run("everything")[0]["status"] == "invalid_request"
    result = negotiate(TEXT + "\nsupplier_channel: free_text\nsupplier_channel: mixed\n", seed=1, llm=Client(Oracle()))
    assert result["status"] == "invalid_request"


def test_flag_off_ignores_the_channel_line():
    assert negotiate(TEXT + "\nsupplier_channel: free_text\n", seed=1) == negotiate(TEXT, seed=1)


def test_cli_with_a_misconfigured_provider_warns_and_fails_closed(tmp_path):
    request = tmp_path / "r.txt"
    request.write_text(TEXT + "\nsupplier_channel: free_text\n")
    out = tmp_path / "out.json"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ZAI_", "NEGOTIATOR_LLM", "PAID_"))}
    env.update(NEGOTIATOR_LLM="on", ZAI_API_KEY="sk-should-not-appear")
    proc = subprocess.run([sys.executable, "-m", "negotiator", "--request-file", str(request), "--out", str(out)],
                          cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "LLM unavailable (missing ZAI_BASE_URL, ZAI_MODEL)" in proc.stderr
    assert "sk-should-not-appear" not in proc.stderr + out.read_text()
    result = json.loads(out.read_text())
    assert result["status"] == "no_deal" and result["llm"]["model"] is None


def test_cli_refuses_free_text_when_paid_tasks_are_enabled(tmp_path):
    request = tmp_path / "r.txt"
    request.write_text(TEXT + "\nsupplier_channel: free_text\n")
    out = tmp_path / "out.json"
    replies = tmp_path / "replies.json"
    replies.write_text("[]")
    env = {**os.environ, "NEGOTIATOR_LLM": "on", "NEGOTIATOR_LLM_PROVIDER": "fake",
           "NEGOTIATOR_LLM_FAKE_REPLIES": str(replies), "PAID_TASKS_ENABLED": "true"}
    subprocess.run([sys.executable, "-m", "negotiator", "--request-file", str(request), "--out", str(out)],
                   cwd=ROOT, env=env, check=True, capture_output=True)
    assert json.loads(out.read_text())["status"] == "invalid_request"
