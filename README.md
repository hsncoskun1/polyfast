# Polyfast

Polymarket Crypto Up/Down 5M event trading bot.

Local-first, single-user trading application that automatically discovers, monitors, and trades 5-minute crypto events on Polymarket.

## Status

**v0.2.6** — Faz 2 in progress (Session & Discovery)

### Completed

**Faz 1 (v0.1.0-v0.1.7):** Foundation — FastAPI skeleton, config loader, SQLite persistence, structured logging with credential masking, frontend skeleton, docs/contracts.

**Faz 2 progress:**
- v0.2.0: Auth client separation (Public / Trading / Relayer)
- v0.2.1: Balance fetch + startup guard
- v0.2.2: Session accounting bootstrap
- v0.2.3: Discovery engine skeleton (candidate discovery, not yet live-validated)
- v0.2.4: Event registry skeleton (7-state machine)
- v0.2.5: Live validation (event liveness check)
- v0.2.6: Safe sync (controlled registry update, soft-remove, open position protection)

### Not yet completed
- v0.2.7: Persistence expansion (next)
- v0.2.8: Faz 2 final tests + delivery report
- Faz 3+: Market data, PTB, rule engine, execution, UI

### Important notes
- Discovery currently finds **candidate** 5M events. Live-validated discovery confirms event liveness but does **not** validate market data, PTB, or prices.
- No live API testing has been performed yet. Codebase uses mock-based unit tests.
- 173 backend tests, all passing.

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
