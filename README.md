# FarmPilotAI

> Production-style **autonomous Web3 farming agent**.
> Async Python • FastAPI • Playwright • web3.py • SQLAlchemy • Pydantic v2

FarmPilotAI scans Web3 projects, drafts a per-wallet farming strategy, drives
a real browser (with MetaMask / Rabby loaded as an extension), executes
faucets / quests / swaps / bridges, and produces a report — all through a
clean, modular, dependency-injected architecture.

This repository is a **starter implementation**: every layer is real,
testable Python, but the network-touching call sites are guarded so the
example runs end-to-end on a vanilla machine with no chain access.

---

## Table of contents

- [Architecture at a glance](#architecture-at-a-glance)
- [Folder structure](#folder-structure)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Running the example workflow](#running-the-example-workflow)
- [Running the FastAPI server](#running-the-fastapi-server)
- [Wallet extension setup](#wallet-extension-setup)
- [Anti-sybil & safety posture](#anti-sybil--safety-posture)
- [Development](#development)
- [Roadmap](#roadmap)
- [Disclaimer](#disclaimer)

---

## Architecture at a glance

```
┌────────────────────────┐    ┌──────────────────────────────┐
│        FastAPI         │    │           Scripts            │
│  /projects /strategies │    │  init_db.py  run_workflow.py │
│  /tasks /wallets /…    │    └──────────────────────────────┘
└──────────┬─────────────┘                 │
           ▼                               ▼
┌──────────────────── ServiceLayer ─────────────────────────┐
│  ProjectService · StrategyService · ExecutionService      │
└──────────┬────────────────────────────────────┬───────────┘
           ▼                                    ▼
   ┌───────────────┐                  ┌──────────────────┐
   │ Agents        │                  │ Task Engine      │
   │ ScannerAgent  │                  │ TaskQueue (N×)   │
   │ PlannerAgent  │  ───── plans ──▶ │ Handlers         │
   │ ExecutorAgent │                  │  faucet / quest  │
   │ RiskAgent     │                  │  swap / bridge   │
   └──────┬────────┘                  └────────┬─────────┘
          ▼                                    ▼
  ┌──────────────┐                  ┌─────────────────────┐
  │ AI Reasoner  │                  │ BrowserManager      │
  │ heuristic /  │                  │ Playwright + stealth│
  │ openai /     │                  │ + Wallet Extension  │
  │ anthropic    │                  │ + SelectorEngine    │
  └──────────────┘                  └────────┬────────────┘
                                             ▼
                                   ┌─────────────────────┐
                                   │ WalletConnector     │
                                   │ EVMClient · Signer  │
                                   └─────────────────────┘

         ┌──────────────────── Storage ─────────────────────┐
         │ SQLAlchemy 2.0 async + aiosqlite (default)       │
         │ Project · Wallet · Strategy · Task · Report      │
         └───────────────────────────────────────────────────┘
```

Cross-cutting:

- **`app.config`** — typed Pydantic settings (env-driven, no globals).
- **`app.container`** — process-wide DI container that lazily constructs
  every singleton (DB, browser, AI reasoner, task engine).
- **`app.core`** — logging, retry/backoff, humanizer, exception hierarchy.

## Folder structure

```
FarmPilotAI/
├── README.md
├── requirements.txt
├── pyproject.toml
├── .env.example
├── app/
│   ├── main.py                 # FastAPI entrypoint
│   ├── config.py               # Pydantic settings (env-driven)
│   ├── container.py            # Dependency-injection container
│   ├── api/
│   │   ├── deps.py             # FastAPI Depends wiring
│   │   └── routes/             # /projects /strategies /tasks /wallets /reports
│   ├── core/
│   │   ├── logging.py          # structlog setup
│   │   ├── retry.py            # RetryPolicy + with_retry
│   │   ├── humanize.py         # human-like delays / typing cadence
│   │   └── exceptions.py
│   ├── db/
│   │   ├── base.py             # DeclarativeBase + naming convention
│   │   ├── session.py          # async engine + session factory
│   │   └── repositories/       # Project / Wallet / Strategy / Task / Report
│   ├── models/
│   │   ├── orm.py              # SQLAlchemy models
│   │   └── schemas.py          # Pydantic v2 schemas
│   ├── agents/
│   │   ├── base.py             # BaseAgent
│   │   ├── scanner.py          # URL → ProjectCreate
│   │   ├── planner.py          # Project → Strategy + PlanItems
│   │   ├── executor.py         # PlanItem → handler dispatch
│   │   └── risk.py             # hard rules + LLM verdict
│   ├── ai/
│   │   ├── reasoner.py         # HeuristicReasoner / OpenAI / Anthropic
│   │   ├── prompts.py
│   │   └── strategy.py         # Plan synthesis
│   ├── browser/
│   │   ├── manager.py          # Playwright + persistent profiles
│   │   ├── profile.py
│   │   ├── extension.py        # MetaMask / Rabby driver
│   │   ├── selectors.py        # self-healing selector engine
│   │   └── stealth.py          # navigator overrides
│   ├── wallet/
│   │   ├── evm.py              # web3.py async wrapper + chain registry
│   │   ├── connector.py        # composite passed to handlers
│   │   └── signer.py           # LocalSigner (HD-derived)
│   ├── tasks/
│   │   ├── engine.py           # Top-level orchestrator
│   │   ├── queue.py            # bounded-concurrency async queue
│   │   └── handlers/           # faucet / quest / checkin / swap / bridge
│   ├── reports/
│   │   └── generator.py        # Markdown digest
│   └── services/               # ProjectService / StrategyService / ExecutionService
├── scripts/
│   ├── init_db.py              # idempotent schema bootstrap
│   └── run_workflow.py         # end-to-end example (hermetic)
├── tests/
│   ├── conftest.py
│   ├── test_humanize.py
│   ├── test_retry.py
│   ├── test_planner.py
│   ├── test_executor.py
│   ├── test_repositories.py
│   └── test_api.py
├── data/                       # SQLite DB (gitignored)
├── profiles/                   # Persistent Chromium profiles (gitignored)
├── extensions/                 # Unpacked wallet extensions (gitignored)
├── logs/                       # Log files (gitignored)
└── reports/output/             # Rendered markdown reports (gitignored)
```

## Quick start

```bash
# 1. Clone and enter
git clone https://github.com/deaasiska22/FarmPilotAI.git
cd FarmPilotAI

# 2. Python 3.12 venv
python3.12 -m venv .venv && source .venv/bin/activate

# 3. Install
pip install -r requirements.txt

# 4. Configure
cp .env.example .env  # then edit

# 5. Initialise the DB
python -m scripts.init_db

# 6. Run the example pipeline (no network, no browser needed)
python -m scripts.run_workflow

# 7. Or boot the API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# open http://localhost:8000/docs
```

> The example workflow swaps the real Playwright handlers for hermetic
> no-ops so it runs on any developer machine. For real browser-driven runs
> see [Wallet extension setup](#wallet-extension-setup).

## Configuration

Every knob lives in `app/config.py` and is overridable via env / `.env`.
Most-frequent edits:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Async SQLAlchemy DSN. Default: `sqlite+aiosqlite:///./data/farmpilot.db` |
| `AI_PROVIDER` | `openai` / `anthropic` / `none` (defaults to deterministic heuristic) |
| `AI_API_KEY` | Required when `AI_PROVIDER ≠ none` |
| `BROWSER_HEADLESS` | Auto-flipped to `false` when an extension is loaded (Chromium limitation) |
| `WALLET_EXTENSION` | `metamask` / `rabby` / `none` |
| `WALLET_EXTENSION_PATH` | Absolute path to the unpacked extension |
| `EXEC_DRY_RUN` | When `true`, swap/bridge handlers stop *before* signing |
| `EXEC_RISK_MAX_USD` | Hard ceiling enforced by the RiskAgent |

## Running the example workflow

```bash
python -m scripts.run_workflow
```

What it does:

1. Bootstraps the SQLite schema.
2. Seeds one `Project` + one burner `Wallet`.
3. Calls `PlannerAgent.run(...)` → produces a `Strategy` + N `PlanItem`s.
4. Persists tasks as `PENDING` and drains them through the `TaskEngine`.
5. Writes `reports/output/strategy-<id>.md`.

## Running the FastAPI server

```bash
uvicorn app.main:app --reload
```

OpenAPI is auto-generated at `/docs`. Key endpoints:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/healthz` | liveness probe |
| `POST` | `/api/v1/projects/scan` | scan URL list → projects |
| `GET/POST` | `/api/v1/projects` | list / register a project |
| `POST` | `/api/v1/strategies/design` | planner-as-a-service |
| `POST` | `/api/v1/strategies/{id}/run` | drain the strategy through the engine |
| `GET` | `/api/v1/tasks/{id}` | inspect a task |
| `GET/POST` | `/api/v1/wallets` | manage wallets |
| `GET` | `/api/v1/reports/strategy/{id}` | latest report row |
| `GET` | `/api/v1/reports/strategy/{id}/markdown` | rendered markdown |

## Wallet extension setup

1. Install Playwright Chromium once:
   ```bash
   playwright install chromium
   ```
2. Download an **unpacked** MetaMask or Rabby extension into
   `./extensions/<name>/` (or anywhere; point `WALLET_EXTENSION_PATH` at it).
3. Set in `.env`:
   ```env
   WALLET_EXTENSION=metamask
   WALLET_EXTENSION_PATH=/abs/path/to/extensions/metamask
   WALLET_DEFAULT_MNEMONIC="word1 word2 ..."
   WALLET_DEFAULT_PASSWORD="strong-password"
   BROWSER_HEADLESS=false
   ```
   > **Headless mode is automatically disabled when an extension is
   > requested** — Chromium does not support extensions in `--headless=new`.
4. Run the workflow. On first launch the BrowserManager will:
   - Spawn Chromium with `--load-extension=…`.
   - Discover the extension via background workers.
   - Import your mnemonic + set the password if the keystore is empty.
   - Stash the profile under `./profiles/<wallet-label>/` so subsequent runs
     skip onboarding.

## Anti-sybil & safety posture

- **Human delays**: every click / key event flows through `Humanizer` —
  randomised window with occasional "thinking" pauses.
- **Self-healing selectors**: each interaction takes a tuple of selectors
  (data-testid → role → text), falling through in order before raising.
- **Stealth init script**: removes `navigator.webdriver`, spoofs plugins /
  languages, and adds canvas noise.
- **Persistent profiles**: cookies, IndexedDB, and the wallet keystore
  survive process restarts so traffic patterns look continuous.
- **Risk gate before signing**: `RiskAgent` enforces a hard USD ceiling and
  consults the reasoner; **fails closed** when the reasoner is unreachable.
- **Dry-run by default**: swap & bridge handlers stop before pressing
  "Confirm" until you explicitly set `EXEC_DRY_RUN=false`.

## Development

```bash
# Run the suite (in-memory SQLite, no network, no browser)
pytest

# Lint
ruff check .

# Type check
mypy app
```

Tests are designed to run on a clean Python 3.12 install with **only**
`pip install -r requirements.txt`. They do not touch the network, the
browser, or any AI provider.

## Roadmap

- Alembic migrations (the scaffold ships `metadata.create_all`)
- Per-chain gas-price oracle inside `EVMClient`
- Snapshot/PIN strategy versioning for reproducible runs
- Pluggable secret vaults (`vault://`, `kms://`) behind `BaseSigner`
- Multi-wallet fanout in the planner
- Prometheus exporter

## Disclaimer

FarmPilotAI is research-grade automation tooling. Web3 farming carries
financial, legal, and ToS risk; you are responsible for ensuring every
action this agent performs on your behalf is allowed by the protocols you
interact with. Treat the dry-run + risk gate defaults as load-bearing.
