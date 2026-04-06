# Polyfast

Polymarket Crypto Up/Down 5M event trading bot.

Local-first, single-user trading application that automatically discovers, monitors, and trades 5-minute crypto events on Polymarket.

## Status

**v0.6.5** — Faz 6 in progress (Exit & Claim/Redeem)

### Completed

**Faz 1 (v0.1.0-v0.1.7):** Foundation — FastAPI, config, SQLite, logging, frontend skeleton, docs.

**Faz 2 (v0.2.0-v0.2.8):** Auth client separation, balance fetch, session accounting, discovery engine, event registry (7-state), live validation, safe sync, persistence expansion.

**Faz 3 (v0.3.0-v0.3.6):** RTDS WebSocket, market mapping, PTB fetch with lock, live price pipeline, snapshot production, persistent coin USD price (150ms resubscribe).

**Faz 4 (v0.4.0-v0.4.6):** Rule engine (6 rules), coin-based settings, side mode (dominant/up/down), discovery loop, eligibility gate, subscription manager, evaluation loop, orchestrator wiring.

**Faz 5 (v0.5.0-v0.5.3):** Order intent, validation, position state machine (6-state), fee-aware PnL, order execution, balance lifecycle, CLOB SDK wrapper, paper mode e2e.

### In Progress

**Faz 6 (v0.6.0-v0.6.5+):** Exit evaluator (TP/SL/force sell), latch + reevaluate, exit executor with retry bands, manual close, claim/redeem lifecycle, settlement orchestrator, relayer wrapper.

### Not yet started
- Faz 7: Recovery (restart, persistence, profiles)
- Faz 8: UI (frontend, settings panel, trade cards)

### Notes
- 673 backend tests, all passing.
- Paper mode only — LIVE_ORDER_ENABLED=False, LIVE_SETTLEMENT_ENABLED=False.
- Registry is in-memory (persistence deferred to Faz 7).

## Tech Stack

- **Backend:** Python 3.12+ / FastAPI
- **Frontend:** React + Vite + TypeScript
- **Storage:** SQLite
- **Test:** pytest (backend), vitest (frontend)

## Quick Start

```bash
# 1. Clone
git clone https://github.com/hsncoskun1/polyfast.git
cd polyfast

# 2. Setup credentials
cp .env.example .env
# Edit .env with your Polymarket API credentials

# 3. Backend
pip install -r requirements.txt
uvicorn backend.main:app --reload

# 4. Frontend
cd frontend
npm install
npm run dev
```

## Project Structure

```
polyfast/
├── backend/          # Python/FastAPI backend (sole authority)
├── frontend/         # React/Vite/TypeScript UI
├── config/           # Configuration files
├── docs/             # Architecture, governance, releases
├── test-results/     # Delivery reports and test outputs
├── tools/            # Diagnostics and debug scripts
└── tests/            # Backend and frontend tests
```

## Architecture

Backend is the single source of truth. Frontend displays backend state and relays user actions. No trading decisions are made in the frontend.
