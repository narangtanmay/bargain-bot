# Evidence Log

## 2026-10-31 - Preprod paid procurement task completed and seller receipt verified

### Sokosumi Task

- Title: **Preprod paid procurement test - valid request**.
- Task ID: `01a190b9-dc73-7549-a1f1-42987c3d0138`. This identifies the successful full-request run; an earlier Task shares the same title.
- Coworker: `Bargain Bot` (current display name; historical Task identity is unchanged) (`01a18f2e-2764-7138-82e3-8e92a235956e`).
- Context: Preprod Personal Workspace (`organizationId: null`).
- Live Core status: `COMPLETED`; local worker phase: `completed`; local payment stage: `settled`.
- Created: `2026-10-31T06:51:02.131Z` (UTC).
- Completion event: `01a190bc-e185-77a8-8217-95871d270f01`, posted by the Coworker at `2026-10-31T06:54:20.037Z` (UTC).

### Request and verified negotiation result

The request asked for 2,000 stainless steel mounting brackets, at most EUR 4.80 per unit, delivery within 21 days, and payment terms net 30.

- Outcome: `deal` with simulated Supplier A.
- Unit price: **EUR 4.31**; total: **EUR 8,620.00** for 2,000 units.
- Delivery: 18 days; payment terms: net 30.
- Supplier's opening unit price: EUR 4.88; simulated saving against that opening quote: **EUR 1,140.00**.
- All **10/10** deterministic checks passed: unit-price cap, optional total cap, strict saving against the winner's opening quote, quantity, delivery, mandatory terms, supplier confirmation, Ed25519 signature, confirmation matching the accepted sheet, and total arithmetic.
- The Ed25519 check verifies the simulated supplier message's integrity. The signer is a demo supplier with a seed-derived key; it does not prove a real supplier's identity or agreement.

### Masumi Payment Service and result integrity

- Network: Cardano Preprod.
- Payment ID: `cmvw1lmo9000n01pbqiobk7y3`.
- Requested negotiation-service fee: `1,000,000` base units (**1 tUSDM**).
- Submitted result SHA-256: `691222cc380239fbb7f079761e7b9d10e195890971040f6a7afe07f9ef3154f9`.
- Recomputed SHA-256 of the original UTF-8 result file exactly matches both the local submitted hash and the live MPS `resultHash`.
- MPS history confirms the lifecycle `FundsLocked -> ResultSubmitted -> Withdrawn`.

### Cardano transaction evidence

- Lock transaction: [`9ae47b91ac40499c864276bf6074f5fdfff1baa9ba613377d0757a725571f6a9`](https://preprod.cardanoscan.io/transaction/9ae47b91ac40499c864276bf6074f5fdfff1baa9ba613377d0757a725571f6a9).
- Result-submission transaction: [`304720bcd352d81cc4360fc71eca66e834f5ffce5d21940205f133606381a221`](https://preprod.cardanoscan.io/transaction/304720bcd352d81cc4360fc71eca66e834f5ffce5d21940205f133606381a221).
- Seller-withdrawal transaction: [`c2d59bd393167e5e47b560bfdb81b1ebeae2041e41e124f5246dac065a20aef0`](https://preprod.cardanoscan.io/transaction/c2d59bd393167e5e47b560bfdb81b1ebeae2041e41e124f5246dac065a20aef0).
- MPS marks all three transactions `Confirmed`. Its withdrawal transaction record was created at `2026-10-31T07:37:37.420Z` (UTC; this is the MPS record timestamp, not an independently measured block timestamp).
- The result-submission transaction's earlier recorded block height was `5356157`, with the MPS `confirmations` field then reporting `0`.
- Explorer links identify the transactions. Live verification below used Sokosumi Core, MPS and Blockfrost; the explorer pages were not independently fetched.

### Settlement verification

Checked `2026-10-31T10:28:39.469Z` (UTC; 31/10/2026, 11:28:39 CET):

- Sokosumi runtime receipt: `claimStatus: PURCHASED`, `onChainState: Withdrawn`, `settled: true`, with the seller-withdrawal hash above.
- The receipt's payment identifier matches the original worker journal. Live MPS reports `Withdrawn` and has a matching `Confirmed` withdrawal transaction with the same hash.
- Blockfrost transaction inputs/outputs for that exact withdrawal hash were checked at the dedicated seller address:
  - Address: `addr_test1qp0rdp08gdtvv3kgtk5f58q6wxy9aqfqelhnz20qt7cg7zpsm9anrfqe72we4z8ajtech4l3dn8qdukhrv86mtnlh8xqwdctrg`.
  - Asset unit: `16a55b2a349361ff88c03788f93e1e966e5d689605d044fef722ddde0014df10745553444d`.
  - Seller inputs: `0` base units; seller outputs: `1000000` base units.
  - **Net seller receipt: +1,000,000 base units (1 tUSDM).** This subtracts seller inputs rather than counting change as new payment.
- The Core receipt's `withdrawnForSeller` array was empty. The payout amount above is established by the independently read transaction inputs/outputs, rather than inferred from that array. The original local journal also records `settlement.verified: true`.

This establishes a completed Sokosumi Task, a matching submitted result hash, and a verified **Preprod negotiation-service fee payout**. The suppliers and commercial negotiation are simulated. No physical goods, real supplier invoice, or delivery were verified; the EUR 8,620 simulated order total was not paid through this escrow. Cardano/Masumi settlement does not validate the commercial quote.

### Historical snapshot - before seller withdrawal

The earlier MPS check at `2026-10-31 08:00:32.952 CET` (`07:00:32.952 UTC`) observed `ResultSubmitted`, with zero seller withdrawals and zero buyer withdrawals. That snapshot preceded the withdrawal verified above.

- Result deadline: `2026-10-31 08:11:08.730 CET` (`07:11:08.730 UTC`).
- Unlock time: `2026-10-31 08:27:08.730 CET` (`07:27:08.730 UTC`).
- External dispute unlock: `2026-10-31 08:43:08.730 CET` (`07:43:08.730 UTC`).

### Local evidence and verification sources

The original paid-run artifacts are in the ignored `.local/` directory of the `team-negotiation-chat` checkout: `01a190b9-dc73-7549-a1f1-42987c3d0138.json` (journal), `01a190b9-dc73-7549-a1f1-42987c3d0138.txt` (result), and `01a190b9-dc73-7549-a1f1-42987c3d0138-negotiation.json` (structured quote and checks). These paths are relative to that original checkout; the private artifacts were not copied into Git. The current checkout has a new ignored, credential-free verification snapshot at `.local/paid-task-evidence-check.json`.

Read-only checks used:

```powershell
sokosumi.cmd --preprod tasks get 01a190b9-dc73-7549-a1f1-42987c3d0138 --json
sokosumi.cmd --preprod runtime receipt 01a190b9-dc73-7549-a1f1-42987c3d0138 --coworker-id 01a18f2e-2764-7138-82e3-8e92a235956e --json
```

The MPS resolve endpoint and Blockfrost transaction-UTXO endpoint were queried with the existing private runtime/read configuration. No new Task, payment, withdrawal, registration, or deployment was performed for this evidence update. No credential values or private keys are included here.

## 2026-10-31 - Integration JSON demo completed (unpaid)

- Integration commit: `13aeaca` on `adrian/integration-paid-mock-verifier`.
- Sokosumi Preprod Personal Workspace Task: `01a190fa-422a-724a-91c0-9bf58ef73680`, named `Integration demo - JSON procurement - unpaid`.
- Created at `2026-10-31T08:01:22.474Z`; completion event `01a190fa-56f0-71ef-ba0b-108d7db18ba1` at `2026-10-31T08:01:27.792Z`.
- Core Task detail and the local journal both confirmed `COMPLETED`; local negotiation outcome was `deal`. The JSON description remained valid and reached the Python request adapter as structured data.
- Simulated Supplier A: 2,000 brackets at EUR 4.31 per unit, EUR 8,620 total, delivery 18 days versus the 21-day cap, payment terms net 30. Simulated savings versus that supplier's opening quote: EUR 1,140. All ten commercial and signature checks passed.
- The integrated worker ran with `MOCK_AGENT=false` and `PAID_TASKS_ENABLED=false`. This exercised the actual local negotiator/checker and live Sokosumi start/completion, without an MPS payment or real supplier contact. Demo supplier signatures establish demo-message integrity, not a real supplier's identity.
- Ignored local evidence: `.local/01a190fa-422a-724a-91c0-9bf58ef73680.json`, the matching `.txt` result, and `.local/01a190fa-422a-724a-91c0-9bf58ef73680-negotiation.json`. Runtime evidence and credentials are not committed.
- The demo worker was stopped at the operator's request after completion. No project worker remained running at the final process check.
