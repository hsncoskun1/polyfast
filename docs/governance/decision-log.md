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

### DEC-002 — Spread rule: default disabled, admin-only controls

- **Date:** 2026-04-07
- **Status:** Accepted
- **Context:** Spread giris kurali bazi pazar kosullarinda yanliligiga meyilli bir sinyal; siradan bir kullanicinin kurali acip kapatabilmesi hatali kurulum riskini dogurur. Urun sahibi riskli kurallarin normal kullanici icin default gorunmez ve kontrol disi olmasini istedi.
- **Decision:**
  - Spread rule normal kullanici tarafinda **default disabled** olarak gelir
  - Normal kullanici kurali dogrudan **acip kapatamaz, editleyemez, varsayilan olarak goremez**
  - Advanced admin paneli 3 ayri bayragi kontrol eder:
    1. `visible` — kullaniciya gosterilsin mi
    2. `toggleable` — kullanici acip kapatabilsin mi
    3. `editable` — kullanici esigi degistirebilsin mi
  - Config schema'da `rules.spread` altinda `default_enabled: false` + `admin_controls: {visible, toggleable, editable}` namespace'i bulunur
  - Rule engine tarafinda disabled spread rule `RuleState.disabled` doner ve `signal_ready` hesabina dahil edilmez (v0.8.0-backend-contract davranisiyla uyumlu)
- **Consequences:**
  - Settings modal (Faz 8) spread kuralini default listelemez
  - Advanced admin paneli gelecek bir fazda expose edilir (henuz impl yok)
  - Bu karar gerceklesene kadar spread rule **hardcoded disabled** olarak kalabilir; her delivery report'ta HARDCODED ADMIN SETTINGS basliginda isaretlenmelidir
  - Rule toggle altyapisi (Faz 4) bu kuralin ayni enable/disable API'si ile calisir; yalnizca UI expose'u farklidir
- **Supersedes:** —
