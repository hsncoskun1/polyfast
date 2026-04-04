# Data Sources Contract

## External Data Sources

### 1. RTDS WebSocket (Live Prices)

- **Provides:** Real-time bid/ask/last prices for active markets.
- **Protocol:** WebSocket (`wss://`).
- **Auth:** None (public feed).
- **Failure behavior:** Backend marks all dependent markets as `STALE`. No orders placed on stale data. Reconnect with exponential backoff (1s, 2s, 4s, max 30s). Frontend shows "Price Feed Disconnected" status.

### 2. `__NEXT_DATA__` / API (PTB -- Position Token Balance)

- **Provides:** Current token balances per market position.
- **Protocol:** HTTP GET (page scrape or API endpoint).
- **Auth:** Session cookies / API key depending on endpoint.
- **Failure behavior:** PTB values frozen at last known good. Backend flags positions as `PTB_STALE`. No new orders on markets with stale PTB. Retry every 30s.

### 3. Relayer API (Claims)

- **Provides:** Claim submission and status tracking for resolved markets.
- **Protocol:** HTTP POST/GET.
- **Auth:** API key + signature (api_key, api_secret, api_passphrase).
- **Failure behavior:** Claim queued for retry. No claim is silently dropped. Backend logs every attempt and failure. Max 10 retries with 60s intervals, then alert. Unclaimed funds tracked in accounting.

### 4. Polymarket API (Discovery + Balance)

- **Provides:** Market discovery (event list, metadata), USDC balance.
- **Protocol:** HTTP REST.
- **Auth:** API key for authenticated endpoints; public endpoints unauthenticated.
- **Failure behavior:**
  - *Discovery:* Cached event list used. No new markets added. Stale flag set.
  - *Balance:* Last known balance used. No new orders until balance confirmed. Backend flags `BALANCE_UNCONFIRMED`.

## Universal Rules

- All external calls are made exclusively by the backend.
- Every call is logged with timestamp, endpoint, response code, and latency.
- No external failure is silently ignored. See `external-connectivity-failure-policy.md`.
