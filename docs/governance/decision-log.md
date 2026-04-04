# Decision Log

## Format

Each entry follows this structure:

```
### DEC-{NNN} — {Title}
- **Date:** YYYY-MM-DD
- **Status:** Accepted | Superseded | Deprecated
- **Context:** Why this decision was needed.
- **Decision:** What was decided.
- **Consequences:** What follows from this decision.
- **Supersedes:** DEC-{NNN} (if applicable)
```

Entries are append-only. Decisions are never deleted; they are superseded by newer entries that reference the original.

---

## Entries

### DEC-001 — Tech stack: Python/FastAPI + React/Vite/TS + SQLite

- **Date:** 2025-06-01
- **Status:** Accepted
- **Context:** The Polyfast trading bot requires a backend capable of low-latency decision-making, a responsive frontend for monitoring, and a lightweight persistent store that avoids external database dependencies during single-operator deployment.
- **Decision:** Backend is Python 3.12+ with FastAPI. Frontend is React 18 with Vite and TypeScript. Persistence layer is SQLite via aiosqlite.
- **Consequences:**
  - All trading logic, risk checks, and state management live in Python.
  - Frontend is a pure display/relay layer with no autonomous decision capability.
  - SQLite file is the single persistence artifact; backup = copy one file.
  - No ORM; raw SQL with typed helpers for auditability.
