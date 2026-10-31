# Bargain Bot quickstart

Branch: `negotiation-coworker` (includes the tactician and Adrian integration). Tested on Windows with Node 24.20.0, Python 3.13.2, and cryptography 50.0.2. The unpaid workflow uses the real deterministic negotiator and verifier against simulated suppliers. It does not need a model-provider key, wallet, payment registration, or running Masumi Payment Service.

## Install locally

Install Node.js 24+ and a working Python interpreter first. In PowerShell, from the repository:

```powershell
git fetch origin
git switch --track origin/negotiation-coworker
npm.cmd ci
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r negotiator/requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

If that branch already exists locally, use `git switch negotiation-coworker`. On macOS/Linux use `python3`, `.venv/bin/python`, and `npm` in place of the Windows commands.

## Test without a Sokosumi account

```powershell
$env:PYTHON_BIN = (Resolve-Path .venv/Scripts/python.exe).Path
npm.cmd test
npm.cmd run test:unpaid
```

On macOS/Linux: `export PYTHON_BIN="$PWD/.venv/bin/python"`, then run the same npm scripts. The unpaid integration test completes local fixture tasks with injected completion calls; it makes no external requests. No credentials or private files are required. To run the Python tests too, install the tested dev tool with `python -m pip install pytest==9.2.0` inside the venv, then run `python -m pytest -q` from `negotiator/`.

## Run a live unpaid Sokosumi Task

Use Sokosumi CLI 1.0.4 and follow the account/Coworker/runtime-key setup in [README.md](README.md#connect-your-sokosumi-coworker). Verify your account with `sokosumi --preprod auth whoami --json`. The worker uses the Coworker's runtime credential, configured through the supported CLI; login alone does not configure it. Keep secrets in the supported vault or ignored local configuration. Do not copy another checkout's private files.

Edit `.env` with:

```dotenv
COWORKER_ID=YOUR_COWORKER_ID
PYTHON_BIN="C:/absolute/path/to/this/checkout/.venv/Scripts/python.exe"
MOCK_AGENT=false
NEGOTIATOR_LLM=off
NEGOTIATOR_TACTICIAN=off
PAID_TASKS_ENABLED=false
SOKOSUMI_ORGANIZATION_ID=
SOKOSUMI_ORGANIZATION_SLUG=
```

Use an absolute path to your own Python interpreter; Linux/macOS use the venv's `bin/python`. Leave organization selectors blank for Personal Workspace. Organization setup is described separately in README.

Start the worker in a terminal and leave it open:

```powershell
npm.cmd run worker
```

In Sokosumi Preprod, select your Personal Workspace, assign a new Task to your Coworker, paste the following as its description, and make it READY:

```json
{"item":"stainless steel mounting bracket","quantity":2000,"max_unit_price_eur":4.8,"max_total_eur":9600,"delivery_days":21,"must_haves":["delivery within deadline","payment terms net 30"],"scenario":"normal"}
```

The demonstrated result is a simulated deal with Supplier A at EUR 4.31/unit, EUR 8,620 total, and all ten checks passing. The Task should become COMPLETED. The full result and journal are written under ignored `.local/`. This does not contact a real supplier or make a payment. To demonstrate rejection, use `"scenario":"broken_quote"` or `"scenario":"above_cap"`: expect `no_deal`.

Run only one worker per Coworker across all teammates and checkouts. Agree who operates it if sharing a Coworker. Press Ctrl+C to stop the foreground worker. Paid execution is a separate setup and validation step; keep payments disabled for this guide.
