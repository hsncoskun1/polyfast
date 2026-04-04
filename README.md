# Polyfast

Polymarket Crypto Up/Down 5M event trading bot.

Local-first, single-user trading application that automatically discovers, monitors, and trades 5-minute crypto events on Polymarket.

## Status

**v0.1.0** — Foundation phase (Faz 1)

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
