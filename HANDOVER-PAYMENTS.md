# Bargain Bot payments and Coworker handover

Updated: 2026-10-31

## Freeze integration - 2026-10-31 09:25 CET

Tanmay's ordered merge is green before the 09:50 CET stop time. Main's tactician merge is `f24728a` (parents `6fac749`, `f952cf5`), with its report in `79d5501`. Adrian explicitly approved the worker conflict choices in this conversation before resolution. Step 2 combines that main with Adrian's exact `89eeb65`.

- Preserved main's silent/no-offer fix, paid startup guard, tactician default-off/paid-off behavior, deterministic `followup.mjs`, and deal-only result-hash rule. Protected engine/checker/follow-up files are unchanged from step-1 main.
- Preserved Adrian's Windows CLI adapter, structured JSON input, unpaid lifecycle, all handover/evidence/setup documents, and `Bargain Bot` registration name (branding updated after the freeze). Dropped `skills-lock.json` and `.agents/skills/`.
- Required suites: 67 Node tests pass natively on Windows and in isolated Linux Node 24.20.0; 205 Python tests pass. All 9 local unpaid integration tests pass. All five flag-off example result files remain byte-identical to pre-merge main `6fac749`.
- The full unpaid worker entry point starts and polls with the supported CLI adapter in a synthetic runtime fixture, on Windows and Linux. The existing paid-without-configuration startup refusal remains tested. The smoke workers terminate after testing; no live Task, payment, or model call was made during this freeze merge.
- The existing startup fixture was made platform-aware (.cmd plus System32 on Windows), with one regression covering unpaid startup. No production CLI behavior was changed for the test.
- NegMAS is untouched and remains dev-only. No private configuration, credentials, runtime logs, or keys are committed. Earlier live-demo and payment evidence below remains historical; this freeze validation does not establish a new paid run or seller payout.

## Integration update — 2026-10-31

Integration branch: `adrian/integration-paid-mock-verifier`, based on `test_branch` at `f08975f`, incorporating `adrian/sokosumi-mock-task` at `b512725`. The following original handover describes the earlier mock milestone; its payment status and test counts are historical.

- The payment implementation and follow-up result storage from `test_branch` are retained. `EVIDENCE.md` records the prior Preprod lock and confirmed result-submission transaction; it does not establish seller withdrawal.
- Saket's checker is already part of this base branch. There is no standalone `verify` command. The integration consumes its ten-check result contract without changing the buyer, checker, or signing logic.
- Structured JSON now reaches the Python request adapter unchanged, with canonical field names and procurement aliases documented in `CONTRACT.md`. Mock mode preserves the exact input and parsed object. Malformed JSON is rejected.
- Worker and agent-API payment paths refuse newly generated deals without the full passing verification contract. The unpaid lifecycle is covered locally using actual Python and simulated Task completion.
- The Windows permission assertion is platform-aware; POSIX permission assertions remain active on POSIX. The fake-interpreter tests now run on Windows through Node directly.
- No external task, payment, registration, supplier contact, or deployment was performed during this integration. Payment configuration and live payment revalidation remain separate follow-up work.

Validation on Windows for this integration:

- `npm.cmd test`: 63 passed, 0 failed, 0 skipped.
- Python `pytest` suite in `negotiator/`: 78 passed (Python 3.13.2, cryptography 50.0.2). A fresh ignored project-local `--basetemp` was used because the pre-existing shared pytest temp folder denied access.
- `npm.cmd run test:unpaid` with `PYTHON_BIN` pointing at the existing pinned environment: 9 passed, 0 failed, 0 skipped. This is local integration evidence, not a new live Sokosumi completion or transaction.

Remaining: review this integration, confirm this checkout's own private runtime/payment configuration, then authorize and measure a live revalidation of the existing payment flow. Do not treat the older payment-setup checklist below as proof that working code is absent.

## Live integration demo and shutdown

The integrated worker subsequently completed unpaid JSON Task `01a190fa-422a-724a-91c0-9bf58ef73680` in Sokosumi Preprod, confirmed by completion event `01a190fa-56f0-71ef-ba0b-108d7db18ba1`. The simulated deal was EUR 4.31/unit, EUR 8,620 total, with all ten checks passing. See `EVIDENCE.md` for measured details and `TEAM-QUICKSTART.md` for teammate setup.

This live unpaid demo occurred after the code-integration checks above. The worker was stopped at the user's request, and its runtime lock was cleared after exit. No project worker remained running. New paid execution, seller withdrawal, and physical delivery remain unverified by this demo. The tested integration is ready to share as its own branch.

## Mock execution milestone

- Preprod Vendor: `Procurement Demo` (`01a18f2d-8e2c-704a-bb58-cffb9d8da7c7`).
- Private Coworker: `Bargain Bot` (current display name; the stable Coworker ID is unchanged) (`01a18f2e-2764-7138-82e3-8e92a235956e`), `tasks` capability, not whitelisted publicly.
- Personal Workspace access: `GRANTED` (`01a18cec-5db8-7530-9f83-e7914c3bd6d0`).
- Completed execution-only Task: `01a18f44-2e73-72af-9677-09a137345175`.
- Sokosumi showed the result and `COMPLETED`. The worker's local journal also records `phase: completed`, `status: COMPLETED`, the Coworker ID, and Personal context (`organizationId: null`).
- Local evidence is under ignored `.local/`: `<task-id>.json` (journal) and `<task-id>.txt` (submitted result). Do not commit `.local/`.
- Runtime credential availability is confirmed by successful runtime start and completion. The Task record does not establish how many times key import was attempted; never inspect or copy the vault value.

The result is `MOCK_PROCUREMENT_SIMULATION` / `PROCESSED`, with `NO_DEAL_MOCK_ONLY`, supplier `NOT_CONTACTED`, and payment `NOT_PERFORMED`. There is no supplier quote or confirmation, invoice, transaction hash, or delivery verification. The Task description reached the mock as text; it was preserved verbatim, but its fields were not parsed into structured JSON.

## Commands

Run the deterministic local fixture without a model:

```powershell
npm.cmd run mock -- --input-file mock-procurement-request.json
```

For a Sokosumi Personal Workspace Task, run exactly one worker in a PowerShell terminal and keep it open. These settings keep the worker in mock mode and paid Tasks disabled:

```powershell
$env:COWORKER_ID = '01a18f2e-2764-7138-82e3-8e92a235956e'
$env:MOCK_AGENT = 'true'
$env:PAID_TASKS_ENABLED = 'false'
$env:SOKOSUMI_ORGANIZATION_ID = ''
$env:SOKOSUMI_ORGANIZATION_SLUG = ''
npm.cmd run worker
```

Create a future unpaid execution-only Task from the authenticated Preprod CLI account's default Personal context (do not pass `--personal`; CLI 1.0.4's personal preflight route returned 404 in this setup):

```powershell
sokosumi.cmd --preprod tasks create `
  --coworker-id '01a18f2e-2764-7138-82e3-8e92a235956e' `
  --name 'Procurement mock simulation' `
  --description '{"product":"Demo USB-C barcode scanner","quantity":2,"maximum_unit_price":{"amount":"50.00","currency":"EUR"},"maximum_total_price":{"amount":"100.00","currency":"EUR"},"delivery_deadline":"2026-10-31","mandatory_commercial_terms":["New goods only","Supplier must issue a normal invoice"]}' `
  --status READY `
  --json
```

The Task above has already been created and completed. Check its state before any retry. A read-only detail check is `sokosumi.cmd --preprod tasks get 01a18f44-2e73-72af-9677-09a137345175 --json` from the same authenticated CLI account.

`npm.cmd run api` starts this checkout's existing Masumi Payment Service API integration; it is not required for the mock Task and was not used for this milestone. Do not enable paid Tasks or create a payment as part of mock execution.

## Tests and current limits

- Baseline: 34 of 35 tests passed. The remaining failure is `worker-lock.test.mjs` expecting POSIX mode `0700` (448) while Windows reports `438`; it is a platform-specific permission-mode assertion.
- `npm.cmd run mock -- --input-file mock-procurement-request.json` is the deterministic local check; the completed Sokosumi Task verifies the worker lifecycle and result submission.
- No paid Task, Cardano transaction, supplier API, real negotiation, or physical delivery verification occurred. Keep `PAID_TASKS_ENABLED=false`.

## Next steps

1. Improve Task input encoding/parsing so the JSON request remains structured end-to-end; keep the mock deterministic.
2. Integrate Saket's deterministic verification command and result contract without modifying his verification logic. Only submit verified commercial results.
3. After verification is stable, configure and register the Masumi Payment Service using the existing payment scripts and local ignored configuration. Escrow covers only our negotiation service fee; physical goods remain on the supplier's normal invoice.
4. Before any paid run, confirm registration, runtime permissions, wallet setup, and payment lifecycle with the team. The checker is off-chain; Masumi handles payment/dispute lifecycle and does not validate the commercial quote or physical delivery.
