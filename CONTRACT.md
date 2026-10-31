# Bargain Bot negotiator contract

The Node worker and the Python negotiator meet at one boundary: a CLI call with files.

## Call

```sh
python3 -m negotiator --request-file <path-to-task-text> --out <path-to-result.json> [--seed N] [--scenario above_cap|broken_quote]
```

Run from `negotiator/` (or with that directory on `PYTHONPATH`). The Python environment needs `negotiator/requirements.txt` (`cryptography`, for supplier signatures). Exit code 0 means the JSON file was written, whatever the outcome. Non-zero means a crash; the worker treats it as `error`.

`--scenario` is test plumbing: it steers only the simulated suppliers (`above_cap` raises their floors above the cap; `broken_quote` makes the winner's signed confirmation carry a wrong total). It never reaches the buyer or the checker.

## Input: Task text

The Sokosumi Task description. The negotiator parses these fields, one per line, case-insensitive keys, any order:

```
item: stainless steel mounting bracket
quantity: 2000
max_unit_price_eur: 4.80
delivery_days: 21
must_have: delivery within deadline
must_have: payment terms net 30
```

`item`, `quantity`, `max_unit_price_eur` and `delivery_days` are required. Missing or malformed required fields give `status: "invalid_request"`. Unknown lines are ignored.

Optional lines:

- `max_total_eur: <EUR>`: a cap on the order total. The buyer's unit ceiling becomes the stricter of `max_unit_price_eur` and `max_total_eur / quantity`. A non-positive or non-numeric value gives `invalid_request`.
- `must_have:` may repeat. A structured rule `<field> <op> <value>` (ops `<= < >= > == !=`, for example `must_have: payment_terms_days >= 30`) compares that quote field exactly; a field the quote does not carry fails. Free text stays supported: payment phrases ("net 30") compare payment days, delivery or deadline phrases compare delivery days, anything else must have all its words in the quote's terms.
- `supplier_quote: <supplier name> = <unit price in EUR>` exactly three times (for example `supplier_quote: Print Shop Nord = 14.90`). The three real prices become the suppliers' opening offers, in line order, under those names; the negotiation rounds, delivery and payment terms stay simulated. Combining it with the `above_cap` scenario gives `invalid_request`. Any other count, a missing `=`, an empty name or a non-positive price gives `invalid_request`.

## JSON requests

Task descriptions may also be JSON objects. Node writes their original UTF-8 text unchanged to the Python request file. The Python input adapter maps JSON fields into the existing request parser; the buyer, signature verification, and commercial checks are unchanged.

```json
{"item":"stainless steel mounting bracket","quantity":2000,"max_unit_price_eur":4.8,"max_total_eur":9600,"delivery_days":21,"must_haves":["payment terms net 30"],"scenario":"normal"}
```

JSON uses the same required scalar fields as text, with arrays for `must_haves` and optional `supplier_quotes` (three objects with `name` and `unit_price_eur`). The Node adapter passes JSON `scenario` to the existing CLI scenario flag. Direct Python CLI callers still supply `--scenario`.

The procurement fixture's names are also accepted: `product`, `maximum_unit_price` / `maximum_total_price` as `{"amount":"4.80","currency":"EUR"}`, and `mandatory_commercial_terms`. Prices support EUR only. An absolute `delivery_deadline` is converted to calendar days from `request_date` (ISO YYYY-MM-DD; defaults to the current UTC date). The deadline must be later than that date. Supply `request_date` for reproducible deadline-based runs, or use `delivery_days`. Explicit canonical fields take precedence over their aliases. String fields and terms must fit on one line.

Malformed JSON, arrays, invalid fields, expired deadlines, and missing required values give `invalid_request`. Mock mode preserves the decoded object and the exact original input text without interpreting commercial fields or generating a quote.

## Deal rule

A deal needs both: the price is at or below the caller's caps (`max_unit_price_eur`, and `max_total_eur` when given), and it is **strictly below the winning supplier's own opening quote**, so every deal saves the caller money. A price equal to the opening quote is `no_deal`. The buyer's accept gate runs the same per-sheet checks as the checker, so the two cannot disagree on terms.

## Output: result JSON

```json
{
  "status": "deal | no_deal | invalid_request",
  "opening_prices_source": "provided | simulated",
  "request": {"item": "...", "quantity": 2000, "max_unit_price_eur": 4.8, "delivery_days": 21, "must_haves": ["..."]},
  "quote": {
    "supplier": "Supplier A",
    "unit_price_eur": 4.31,
    "quantity": 2000,
    "total_eur": 8620.0,
    "delivery_days": 18,
    "payment_terms_days": 30,
    "terms": ["certificate of conformity", "DAP delivery", "ISO 9001 certified"],
    "confirmation": {
      "supplier_id": "A", "supplier": "Supplier A", "quote_id": "Q-A-cff1806cc2", "term_sheet_id": "A-5",
      "unit_price": 4.31, "quantity": 2000, "total": 8620.0, "currency": "EUR", "delivery_days": 18,
      "payment_terms_days": 30, "terms": ["..."], "text": "Supplier A confirms order Q-A-cff1806cc2 ...",
      "signature": "<Ed25519, hex>"
    }
  },
  "opening_best_unit_price_eur": 4.88,
  "winner_opening_unit_price_eur": 4.88,
  "savings_eur": 1140.0,
  "checks": [{"name": "unit_price_within_cap", "passed": true, "detail": "4.31 <= 4.80"}],
  "transcript": [{"round": 2, "supplier": "Supplier A", "from": "buyer|supplier", "text": "...", "unit_price_eur": 3.9}],
  "log_hash": "<sha256 hex of the negotiation log>",
  "public_keys": {"Supplier A": "<Ed25519 public key, hex>", "Supplier B": "...", "Supplier C": "..."},
  "summary_markdown": "..."
}
```

(Values from `negotiator/examples/request.txt` with `--seed 1`.)

- `quote` is null unless `status` is `deal`. Its numbers are taken from the supplier's signed confirmation.
- `status` is `deal` only when the buyer accepted a sheet and every entry in `checks` passed. `checks`, in this order: `unit_price_within_cap`, `total_within_max` (passes when no `max_total_eur` is given), `price_below_opening_quote`, `quantity_matches`, `delivery_within_deadline`, `must_haves_met`, `supplier_confirmation_present`, `confirmation_signature_valid` (Ed25519 against that supplier's key in `public_keys`), `confirmation_matches_accepted_sheet` (sheet ID, price, quantity, delivery, payment terms, terms and total equal the sheet the buyer accepted), `total_consistent`. On `no_deal` the checks describe the best standing offer. If no supplier returns a usable offer, the outcome is `no_deal`, `checks` is empty, both opening price fields and `quote` are null, and savings are 0. The transcript, log hash, public keys, and summary remain available.
- `savings_eur` is `(winner_opening_unit_price_eur - unit_price_eur) x quantity`, always positive on a deal, 0 otherwise. `opening_best_unit_price_eur` is the lowest opening quote among suppliers that meet quantity, delivery and must-haves, for information.
- `log_hash` is the SHA-256 of the canonical JSON of the negotiation threads and the decision trace; the same request and seed give the same hash.
- `opening_prices_source` is `provided` when `supplier_quote` lines were given (the summary then says the opening prices are real quotes and the negotiation rounds, delivery and payment terms are simulated), otherwise `simulated`.
- `summary_markdown` is the human-readable result that the worker posts to Sokosumi and hashes for Masumi.
- New fields may be added; existing fields are not renamed or removed. Integrations should key on `status` and `summary_markdown`.

## Node verification gate

`negotiate.mjs` consumes the deterministic checker result from the configured Python negotiator. A `deal` requires a quote, a nonempty summary, and all ten checks listed above in contract order, each with boolean `passed: true`. Missing, failed, duplicate, or malformed checks produce `error`. The worker and agent API enforce this gate before a new payment result is prepared; a summary changed after verification is rejected too. This checks the subprocess result contract; it is not a second cryptographic verifier or independent supplier authentication. Configure only a trusted local negotiator.

## Payment rule (worker side)

- `deal`: submit the result hash, complete the Task, seller collects after the dispute window.
- `no_deal`, `invalid_request`, `error`: never submit a result hash. Post the summary as a comment and complete the Task without a result submission, so the buyer's escrow is refunded after `submitResultTime`.

The negotiator never touches payments. Prices are set only by deterministic code; no LLM sets or reads prices.

## Signatures

Each simulated supplier signs its confirmation with its own Ed25519 key; the buyer side holds only the public keys. The keys are derived from the run seed so a seeded run reproduces exactly. The signature therefore proves that a confirmation was not changed after the supplier sent it; it does not prove who the supplier is, because this project operates the demo suppliers.

## LLM adapter (`llm-adapter` branch, off by default)

With `NEGOTIATOR_LLM` unset or not `on`, nothing below applies and the result file is byte-identical to `negotiation-coworker` (pinned in `negotiator/tests/test_flag_off.py`).

With `NEGOTIATOR_LLM=on`:

- An optional `supplier_channel: protocol | free_text | mixed` line selects suppliers that answer in prose: none (the default), all three, or the first one. Any other value, or the line given twice, gives `invalid_request`. `free_text` and `mixed` give `invalid_request` while `PAID_TASKS_ENABLED=true`.
- `NEGOTIATOR_LLM_PROVIDER` picks the model provider: `openai_compatible` (the default, from `ZAI_BASE_URL`, `ZAI_API_KEY`, `ZAI_MODEL`) or `fake` (scripted replies from the JSON list in `NEGOTIATOR_LLM_FAKE_REPLIES`). A misconfigured provider prints a warning to stderr and every model call fails, so free-text replies count as no bid.
- The result gains `supplier_channels` (`{supplier name: "protocol" | "free_text"}`) and `llm` (`{calls, failures, input_tokens, output_tokens, seconds, model}`). Transcript lines from a free-text supplier carry the supplier's own text and `read_error` (null when it was read).
- A free-text supplier has no entry in `public_keys`. Its confirmation is what the reader read from its prose, has `"channel": "free_text"` and no `signature`, and `confirmation_signature_valid` passes with detail `not applicable: free-text supplier, identity not verified`.
- The model reads supplier text and rephrases the buyer's price offers. It sets no price and makes no check: every figure it reads must match the supplier's own words, or the reply counts as `no_bid`.
- `NEGOTIATOR_LLM_PROVIDER=deepseek` uses DeepSeek's OpenAI-format API (`DEEPSEEK_API_KEY`; `DEEPSEEK_BASE_URL` and `DEEPSEEK_MODEL` default to `https://api.deepseek.com` and `deepseek-flash`), in its default thinking mode (`DEEPSEEK_REASONING_EFFORT` none, low, high or max sets the effort). A short answer still gets `DEEPSEEK_MAX_TOKENS` (default 4096) of output, because the thinking counts against it, and each call gets 25 s within a 50 s budget per run. `NEGOTIATOR_LLM_TIMEOUT_S` and `NEGOTIATOR_LLM_BUDGET_S` override the time limits for any provider, at most 30 s and 50 s. `llm` also counts `reasoning_tokens`.
- With `NEGOTIATOR_TACTICIAN=on` as well (ignored while `PAID_TASKS_ENABLED=true`), the model picks each ordinary price offer from a short list that code priced: the engine's own offer (`E0`), a hold, a smaller or larger step, or accepting the cheapest sheet that passes the accept gate. It answers with an option ID only; anything else, a timeout or an API failure sends `E0`. Accepts, walk-aways and last calls stay the engine's, and every move still passes the table's checks. The result gains `tactician`: one entry per offer put to the model, `{supplier, options, chosen, fallback, reason}`. Its prompt carries prices and history only, never the caller's cap.
