# External Connectivity Failure Policy

**This policy is IMMUTABLE. No code change, configuration flag, or runtime condition may bypass these rules.**

## Failure Response Table

| Source | Failure Behavior | Required Action |
|---|---|---|
| **RTDS WebSocket** | All dependent market prices marked `STALE`. | Halt order placement on affected markets. Reconnect with exponential backoff. Surface "Price Feed Down" in UI. |
| **PTB endpoint** | PTB values frozen at last known good. Positions flagged `PTB_STALE`. | Halt new orders on markets with stale PTB. Retry every 30s. Surface "PTB Stale" in UI. |
| **Relayer API** | Claim submission queued. No claim discarded. | Retry up to 10 times at 60s intervals. After max retries, raise alert. Log every attempt. Track unclaimed funds. |
| **Balance API** | Balance marked `UNCONFIRMED`. Last known balance retained. | Halt new orders until balance confirmed. Retry every 15s. Surface "Balance Unconfirmed" in UI. |
| **Auth / Credential** | All authenticated operations suspended. | Surface "Auth Failure" in UI immediately. No retry without user intervention. Log failure reason (not credential values). |

## Core Rules

### Silent Bypass is FORBIDDEN

No failure in any external data source may be silently ignored, swallowed, or worked around. Every failure must:

1. Be logged with timestamp, source, error type, and attempt count.
2. Set the appropriate stale/unconfirmed flag on affected data.
3. Be surfaced to the user via the frontend health display.
4. Trigger the defined retry or halt behavior.

### No Fallback to Stale Data for Decisions

Stale data may be displayed (with a stale indicator) but must never be used as input to trading decisions. If a required data source is unavailable, the dependent operation halts until the source recovers.

### Degraded Mode

The system may continue operating in a reduced capacity when non-critical sources fail:
- Discovery failure: existing markets continue trading; no new markets added.
- PTB failure on one market: other markets unaffected.

Critical source failures (RTDS, Balance, Auth) halt all trading activity.
