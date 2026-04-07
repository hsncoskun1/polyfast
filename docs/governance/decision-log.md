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

### DEC-002 — Spread rule: default disabled, admin-controlled 3-flag policy

- **Date:** 2026-04-07
- **Status:** Accepted
- **Revised:** 2026-04-07 — initial wording softened. Earlier draft "kullanici tamamen kontrol disi" yanlis anlasilmaya acikti; dogru model kullanicinin yetki seviyesinin admin policy bayraklariyla belirlenmesidir.
- **Context:** Spread giris kurali bazi pazar kosullarinda yanliligiga meyilli bir sinyal. Urun sahibi: spread kurali default kapali olsun, kullanicinin etkilesim seviyesi admin policy ile kontrol edilebilsin — admin policy acmadigi surece kullanici gormesin/dokunmasin, ama admin acarsa kullanici da kullanabilsin.
- **Decision:**
  - Spread rule **default disabled** olarak gelir
  - Karar tek bir `enabled` bayragi degildir — birbirinden bagimsiz **3 admin policy bayragi** vardir:
    1. `visible` — kullaniciya UI'da gosterilsin mi (admin-controlled)
    2. `user_toggleable` — kullanici kurali acip kapatabilir mi (admin-controlled)
    3. `user_editable` — kullanici esigi editleyebilir mi (admin-controlled)
  - Kullanici **yetki kadar** etkilesim kurabilir; admin policy acmadan kullanici dokunmaz, admin policy acarsa kullanici dokunabilir
  - Config schema: `rules.spread` altinda `default_enabled: false`, `threshold`, `admin_policy: {visible, user_toggleable, user_editable}` namespace'i bulunur
  - `admin_policy` namespace'i ayri tutulur — normal settings UI bu alanlara erisemez; sadece advanced admin panelinden okunur/yazilir
  - Rule engine tarafinda disabled rule `RuleState.disabled` doner ve `signal_ready` hesabina **dahil edilmez** (v0.8.0-backend-contract `_build_search_tile` davranisiyla uyumlu)
- **Consequences:**
  - Settings modal (Faz 8) `admin_policy.visible=false` iken spread kuralini listelemez
  - `visible=true AND user_toggleable=false` -> kural gri/disabled gosterilir, toggle clickable degildir
  - `visible=true AND user_editable=false` -> esik input read-only render edilir
  - Advanced admin paneli (gelecek faz) `admin_policy` 3 bayragini ve esigi expose eder
  - Bu karar gerceklesene kadar spread rule **hardcoded** policy ile kalabilir: `default_enabled=false, admin_policy={visible:false, user_toggleable:false, user_editable:false}`. Bu interim impl her delivery report'ta HARDCODED ADMIN SETTINGS basliginda isaretlenmelidir
  - Rule toggle altyapisi (Faz 4) ayni enable/disable API'si ile calisir; admin_policy yalnizca UI expose katmaninda devreye girer
- **Supersedes:** —
