import re
from pathlib import Path

import pytest

from negotiator.engine import negotiate
from negotiator.llm import Client, FakeLLM, LLMError
from negotiator.writer import check, write

BODY = "Thank you for your offer. We can offer EUR 4.10 per unit for 2000 units. Another supplier has offered EUR 4.30 per unit."
ROOT = Path(__file__).resolve().parent.parent
ARGS = {"price": 4.10, "rival": 4.30, "quantity": 2000, "delivery_days": 21}


def run(reply, body=BODY, **overrides):
    fake = FakeLLM([reply])
    text, reason = write(Client(fake), body, **{**ARGS, **overrides})
    return text, reason, fake


def test_good_wording_is_sent():
    reply = ("Many thanks for your quote. For the 2,000 units we could go to EUR 4.10 per unit; "
             "for reference, another supplier has offered us EUR 4.30 per unit.")
    text, reason, fake = run(reply)
    assert (text, reason) == (reply, None)
    assert BODY in fake.prompts[0][1]


def test_quotes_and_code_fences_around_the_reply_are_dropped():
    text, reason, _ = run('"We can offer EUR 4.10 per unit for 2000 units. Another supplier has offered EUR 4.30."')
    assert reason is None and not text.startswith('"')


@pytest.mark.parametrize("reply,why", [
    ("We can offer EUR 3.90 per unit. Another supplier has offered EUR 4.30.", "'3.90' is not in the buyer's message"),
    ("We can offer EUR 4.50 per unit. Another supplier has offered EUR 4.30.", "'4.50' is not in the buyer's message"),
    ("Another supplier has offered EUR 4.30 per unit. Could you do better?", "chosen price missing"),
    ("We can offer EUR 4.10 per unit for 2000 units.", "rival price missing"),
    ("We can offer 4.10 per unit. Another supplier has offered EUR 4.30.", "chosen price missing"),
    ("Our budget allows EUR 4.10 per unit. Another supplier has offered EUR 4.30.", "mentions 'budget'"),
    ("We are capped at EUR 4.10 per unit. Another supplier has offered EUR 4.30.", "mentions 'capped'"),
    ("We can offer EUR 4.10 per unit; another supplier has agreed to EUR 4.30.", "mentions 'agreed'"),
    ("This is urgent: EUR 4.10 per unit. Another supplier has offered EUR 4.30.", "mentions 'urgent'"),
    ("Our final offer is EUR 4.10 per unit. Another supplier has offered EUR 4.30.", "mentions 'final'"),
    ("EUR 4.10 per unit, ten percent under another supplier's EUR 4.30.", "mentions 'ten'"),
    ("EUR 4.10 per unit, 5% below another supplier at EUR 4.30.", "mentions '%'"),
    ("EUR 4.10 per unit for 4,100 units. Another supplier has offered EUR 4.30.", "'4,100' is ambiguous"),
    ("", "empty"),
    ("EUR 4.10 per unit. Another supplier has offered EUR 4.30. " + "Thanks. " * 100, "too long"),
])
def test_any_failed_guard_sends_the_template(reply, why):
    text, reason, _ = run(reply)
    assert text == BODY and why in reason


@pytest.mark.parametrize("failure", [LLMError("down"), TimeoutError(), RuntimeError("bug")])
def test_a_model_failure_sends_the_template(failure):
    text, reason, _ = run(failure)
    assert text == BODY and reason


def test_no_client_sends_the_template_without_a_call():
    assert write(None, BODY, **ARGS) == (BODY, "no model configured")


def test_without_a_cited_rival_only_the_chosen_price_is_required():
    body = "Thank you for your offer. We can offer EUR 4.10 per unit for 2000 units."
    text, reason, _ = run("Thanks for the quote. We could do EUR 4.10 per unit for 2000 units.", body=body, rival=None)
    assert reason is None and text.startswith("Thanks")
    text, reason, _ = run("We could do EUR 4.10 per unit; someone else offered EUR 4.30.", body=body, rival=None)
    assert text == body and "'4.30' is not in the buyer's message" in reason


def test_every_message_the_buyer_sends_passes_the_guard_itself():
    request = (ROOT / "examples" / "request.txt").read_text()
    seen = 0
    for seed in range(1, 11):
        for line in negotiate(request, seed=seed)["transcript"]:
            if line["from"] != "buyer" or line["unit_price_eur"] is None:
                continue
            prices = {float(n) for n in re.findall(r"EUR (\d+\.\d\d)", line["text"])}
            rival = next(iter(prices - {line["unit_price_eur"]}), None)
            assert check(line["text"], price=line["unit_price_eur"], rival=rival, quantity=2000, delivery_days=21,
                         rival_required=rival is not None) is None, line["text"]
            seen += 1
    assert seen > 50
