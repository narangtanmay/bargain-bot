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

## 2026-10-31 - Two confirmed buyer refunds: exact Task and payment mapping

Rechecked at **2026-10-31T13:45:44.350Z** (UTC; **14:45:44 CET**). Read-only queries matched the original task journals, live Sokosumi Core tasks/receipts, seller MPS payment histories, and Blockfrost transaction metadata and UTxOs. No new payment, refund, registration, or Task was created for this verification.

Both runs were **paid Personal Workspace tasks** (`organizationId: null`) with a **1 tUSDM** service fee. Both returned **`invalid_request`**, persisted payment stage **`no-result`**, and submitted **no result hash**. They are not evidence of `above_cap` or `broken_quote` paid runs. The request in each case was only `item: stainless steel mounting bracket`; `quantity`, `max_unit_price_eur`, and `delivery_days` were missing.

### Refund 593cb059...

- **Task:** [`01a190b2-02d3-751e-b404-8bf3f8d9c768`](https://preprod.sokosumi.com/tasks/01a190b2-02d3-751e-b404-8bf3f8d9c768); title: **Preprod paid procurement test - valid request**.
- **Task created:** 2026-10-31T06:42:27.667Z (UTC; 07:42:27 CET).
- **Task completed:** 2026-10-31T06:44:43.396Z (UTC; 07:44:43 CET); completion event `01a190b4-1504-743f-8c62-42bdaf9d7522`.
- **Scenario/outcome:** missing required fields / `invalid_request`; `COMPLETED` describes handling the request, not a successful procurement deal.
- **Masumi payment ID:** `cmvw1avdt000h01pbd0za9t7z`.
- **Sokosumi/Masumi agent job ID:** none. Live `tasks jobs` returned `{"jobs":[]}`; this Coworker flow is identified by Task ID and MPS payment ID.
- **Escrow lock:** [`6a4cb4c66049644fd79c939007673ed37b32467e03418de5f3e2807b040d063f`](https://preprod.cardanoscan.io/transaction/6a4cb4c66049644fd79c939007673ed37b32467e03418de5f3e2807b040d063f); block `5356131`, block time **2026-10-31T06:44:30.000Z** (UTC; **07:44:30 CET**). MPS lock transaction record ID: `cmvw1d8f3000j01pbmfvoc7o0`.
- **Buyer refund:** [`593cb059b838870f7e6356914e9022d243fc05a8dc5f2e0972866ec976bb485b`](https://preprod.cardanoscan.io/transaction/593cb059b838870f7e6356914e9022d243fc05a8dc5f2e0972866ec976bb485b); block `5356214`, block time **2026-10-31T07:13:15.000Z** (UTC; **08:13:15 CET**). MPS refund transaction record ID: `cmvw2efhg001001pbk2y8etdp`.
- **MPS refund record created:** 2026-10-31T07:13:32.644Z (UTC; 08:13:32 CET). This service timestamp is distinct from the ledger block time.
- **Result deadline:** 2026-10-31T07:02:46.772Z (UTC; 08:02:46 CET).
- **Verified state:** Core and MPS both report `RefundWithdrawn`; lock and refund transactions are `Confirmed`; MPS `resultHash: null`, with no `ResultSubmitted` transaction.
- **Verified amount:** the refund directly spends output `0` of that Task's original lock transaction; buyer-address outputs minus inputs are **+1,000,000 tUSDM base units = 1 tUSDM**, equal to the requested service fee. Existing input funds returned as change are excluded from the net amount.

### Refund 118f5158...

- **Task:** [`01a190a5-6045-77cb-a9f2-c7eaa8f0ebb7`](https://preprod.sokosumi.com/tasks/01a190a5-6045-77cb-a9f2-c7eaa8f0ebb7); title: **Preprod paid procurement test**.
- **Task created:** 2026-10-31T06:28:39.621Z (UTC; 07:28:39 CET).
- **Task completed:** 2026-10-31T06:35:10.338Z (UTC; 07:35:10 CET); completion event `01a190ab-5682-7319-ba2f-c99551a2c28f`.
- **Scenario/outcome:** missing required fields / `invalid_request`; `COMPLETED` describes handling the request, not a successful procurement deal.
- **Masumi payment ID:** `cmvw0y2lp000a01pbh5ahv5fn`.
- **Sokosumi/Masumi agent job ID:** none. Live `tasks jobs` returned `{"jobs":[]}`; this Coworker flow is identified by Task ID and MPS payment ID.
- **Escrow lock:** [`2f4c817d461323193ee66c32178e9e19ed56cef8fde965412395f395d3b8cac7`](https://preprod.cardanoscan.io/transaction/2f4c817d461323193ee66c32178e9e19ed56cef8fde965412395f395d3b8cac7); block `5356088`, block time **2026-10-31T06:34:59.000Z** (UTC; **07:34:59 CET**). MPS lock transaction record ID: `cmvw10yey000d01pbihdwvulq`.
- **Buyer refund:** [`118f515806654115a3e6e6ecb268a6acb668c4c5fb4590f9a74a14ee06b1dbbb`](https://preprod.cardanoscan.io/transaction/118f515806654115a3e6e6ecb268a6acb668c4c5fb4590f9a74a14ee06b1dbbb); block `5356185`, block time **2026-10-31T07:03:15.000Z** (UTC; **08:03:15 CET**). MPS refund transaction record ID: `cmvw21i8e000x01pbtoe71ful`.
- **MPS refund record created:** 2026-10-31T07:03:29.678Z (UTC; 08:03:29 CET). This service timestamp is distinct from the ledger block time.
- **Result deadline:** 2026-10-31T06:52:49.568Z (UTC; 07:52:49 CET).
- **Verified state:** Core and MPS both report `RefundWithdrawn`; lock and refund transactions are `Confirmed`; MPS `resultHash: null`, with no `ResultSubmitted` transaction.
- **Verified amount:** the refund directly spends output `0` of that Task's original lock transaction; buyer-address outputs minus inputs are **+1,000,000 tUSDM base units = 1 tUSDM**, equal to the requested service fee. Existing input funds returned as change are excluded from the net amount.

The title **“Preprod paid procurement test - valid request”** on the 593cb059... refund is misleading: the live Task description was incomplete. The separate successful paid run with the same title is Task `01a190b9-dc73-7549-a1f1-42987c3d0138`, documented above.

Core receipts report `settled: false` and `txHash: null` for these refunds; `settled` refers to seller payout. Buyer refunds were verified using MPS history and exact lock/refund UTxOs. These are successful ledger refunds after application-level rejection, not failed Cardano transactions. Restoration of Sokosumi credits and ADA fee reimbursement were not established.

## 2026-10-31 - Live TUM-Hackathon runs: deal and no-deal, all unpaid

All runs below belong to **TUM-Hackathon** (`organizationSlug: tum-hackathon-u4ve65`, `organizationId: 01a17942-e6dd-724f-bae6-458b6a0f715a`) and Bargain Bot (`coworkerId: 01a18f2e-2764-7138-82e3-8e92a235956e`). Live Core records and local journals were rechecked at the timestamp above.

| Run | Task ID | Created UTC (CET) | Completed UTC (CET) | Payment |
| --- | --- | --- | --- | --- |
| Carbon steel rods: deal | [`01a1921c-4902-74ef-ab9f-f4ead88d01c4`](https://preprod.sokosumi.com/tasks/01a1921c-4902-74ef-ab9f-f4ead88d01c4) | 2026-10-31T13:18:09.666Z (14:18:09 CET) | 2026-10-31T13:18:18.886Z (14:18:18 CET) | **Unpaid**, 0 credits; no payment/job ID |
| Stainless brackets: no-deal, broken signed total | [`01a19225-3633-74b9-994c-ea1ea00ef0de`](https://preprod.sokosumi.com/tasks/01a19225-3633-74b9-994c-ea1ea00ef0de) | 2026-10-31T13:27:54.676Z (14:27:54 CET) | 2026-10-31T13:28:02.960Z (14:28:02 CET) | **Unpaid**, 0 credits; no payment/job ID |
| Stainless brackets: no-deal, total budget | [`01a19228-076d-7717-b9ca-26363ddcfc35`](https://preprod.sokosumi.com/tasks/01a19228-076d-7717-b9ca-26363ddcfc35) | 2026-10-31T13:30:59.309Z (14:30:59 CET) | 2026-10-31T13:31:06.736Z (14:31:06 CET) | **Unpaid**, 0 credits; no payment/job ID |

- **Carbon steel rods:** 150 units, cap EUR 80/unit, max total EUR 30,000, delivery 50 days, minimum net 40 terms. Simulated Supplier B won at **EUR 76.65/unit**, **EUR 11,497.50 total**, delivery 50 days, net 45; **10/10 checks passed**. Simulated savings against that supplier's EUR 84.64 opening quote: **EUR 1,198.50**. Completion event: `01a1921c-6d06-73cf-9735-6522ebfd1601`.
- **Broken-confirmation no-deal:** explicit `scenario: broken_quote`, seed 1. The demo supplier signed EUR 8,720 for 2,000 units at EUR 4.31, which should total EUR 8,620. The signature passed, but `confirmation_matches_accepted_sheet` and `total_consistent` failed: **8 PASS / 2 FAIL**, outcome `no_deal`, no accepted quote, savings 0. Completion event: `01a19225-5690-7353-8181-c658f3412337`.
- **Total-budget no-deal:** normal scenario (no scenario override), 2,000 brackets, unit cap EUR 6, total cap EUR 8,500, 21 days, net 30. The best standing offer was EUR 4.97/unit = EUR 9,940, exceeding the total cap. `total_within_max` and three confirmation checks failed: **6 PASS / 4 FAIL**, outcome `no_deal`, no accepted quote, savings 0. Completion event: `01a19228-2470-7678-bde7-aaa8479996e1`.

All three completed the real Sokosumi worker / Python verifier flow with **simulated suppliers**, **`PAID_TASKS_ENABLED=false`**, no paid journal state, `totalCredits: 0`, and no linked jobs. **They created no escrow, on-chain result submission, refund, or seller payout.** The paid refunds above occurred earlier in the Personal Workspace; do not attribute those transactions to these TUM no-deal demonstrations.

### Read-only reproduction

```powershell
sokosumi.cmd --preprod tasks get 01a190b2-02d3-751e-b404-8bf3f8d9c768 --json
sokosumi.cmd --preprod tasks jobs 01a190b2-02d3-751e-b404-8bf3f8d9c768 --json
sokosumi.cmd --preprod tasks get 01a190a5-6045-77cb-a9f2-c7eaa8f0ebb7 --json
sokosumi.cmd --preprod tasks get 01a1921c-4902-74ef-ab9f-f4ead88d01c4 --organization-slug tum-hackathon-u4ve65 --json
sokosumi.cmd --preprod tasks get 01a19225-3633-74b9-994c-ea1ea00ef0de --organization-slug tum-hackathon-u4ve65 --json
sokosumi.cmd --preprod tasks get 01a19228-076d-7717-b9ca-26363ddcfc35 --organization-slug tum-hackathon-u4ve65 --json
```

Refund verification additionally used the existing project's scoped MPS credential with `/api/v1/payment/resolve-blockchain-identifier`, and its Blockfrost read credential with `/txs/{hash}` and `/txs/{hash}/utxos`. Credentials, private keys, runtime JSON, and private logs remain outside Git. The CardanoScan URLs identify exact transactions; verification used Core, MPS, and Blockfrost rather than inferring outcomes from an explorer label.
