# Accounting Contract

## Session Lifecycle

1. **Session start:** Backend fetches current USDC balance from Polymarket API. This fetch is **mandatory**. If it fails, the session does not start.
2. **During session:** All balance mutations are tracked via fills. Balance is recalculated as `start_balance + sum(fill_deltas)`.
3. **Session end:** Final balance is fetched and reconciled against calculated balance. Discrepancies are logged.

## PnL Calculation

### Basis: Fill-Price

PnL is always calculated from actual fill prices, never from order prices or market prices.

- **Realized PnL:** Calculated when a position is closed (sell fill) or a market resolves (claim).
  - `realized_pnl = (exit_price - entry_price) * quantity`
- **Unrealized PnL:** Calculated from open positions using current market price.
  - `unrealized_pnl = (current_price - entry_price) * quantity`
- **Total PnL:** `realized_pnl + unrealized_pnl`

Realized and unrealized PnL are always tracked and displayed separately. They are never merged into a single figure without both components being available.

## Price Cap

All prices are capped at **1.00** (backend canonical format). Any external data reporting a price above 1.00 is rejected as invalid.

## Price Format Convention

| Context | Format | Example |
|---|---|---|
| Backend (canonical) | Decimal, 0.00 -- 1.00 | `0.85` |
| Frontend (display) | Integer, 0 -- 100 | `85` |
| Storage (database) | Decimal, 0.00 -- 1.00 | `0.85` |
| WebSocket messages | Decimal, 0.00 -- 1.00 | `0.85` |

The frontend performs the conversion `display = canonical * 100` for rendering only. All calculations, comparisons, and storage use the canonical decimal format.

## Invariants

- No PnL calculation without a confirmed session start balance.
- No realized PnL recorded without a corresponding fill record.
- Unrealized PnL resets to zero when a position is fully closed.
- All monetary values stored with 6 decimal places (USDC precision).
