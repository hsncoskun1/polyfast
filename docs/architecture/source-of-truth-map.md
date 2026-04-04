# Source of Truth Map

Every data domain has exactly one authoritative source. All other consumers read from that source and never cache stale data as truth.

## Authority: Backend (all domains)

| Domain | Authoritative Module | Upstream Source | Notes |
|---|---|---|---|
| Event list | `discovery` service | Polymarket API | Backend fetches, filters, caches. Frontend never queries Polymarket directly. |
| Market data (live prices) | `market_data` service | RTDS WebSocket | Backend maintains WS connection and republishes to frontend via server WS. |
| PTB (Position Token Balance) | `ptb` service | `__NEXT_DATA__` / API scrape | Backend fetches and parses. Single canonical value per token. |
| Balance (USDC) | `balance` service | Polymarket API | Fetched at session start and after every fill. |
| Positions | `position` manager | Derived from fills + PTB | Backend reconciles. Frontend displays only. |
| Orders | `order` manager | Backend order book | All order state lives in backend. Frontend relays user intent. |
| Fills | `fill` tracker | Order execution events | Append-only log in backend. |
| Claims | `claim` service | Relayer API | Backend initiates and tracks claim lifecycle. |
| Rule state | `rule_engine` | Backend config + runtime | All trading rules evaluated server-side. |
| Config | `config` manager | `config.json` / env | Backend loads, validates, serves read-only subset to frontend. |
| Health | `health` monitor | All services | Backend aggregates health from all subsystems. |
| PnL | `accounting` service | Fills + market data | Calculated server-side only. Frontend displays formatted values. |
| Session accounting | `session` manager | Balance snapshots + fills | Session start/end balances, cumulative PnL. Backend only. |
