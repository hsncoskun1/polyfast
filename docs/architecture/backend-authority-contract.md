# Backend Authority Contract

## Core Principle

The backend is the **sole authority** for all trading decisions, state management, and external interactions. The frontend is a display and relay layer only.

## Backend Responsibilities

- Execute all trading logic and risk checks.
- Maintain canonical state for positions, orders, balances, and PnL.
- Hold and use credentials; never expose them to the frontend.
- Manage all external connections (RTDS WS, Polymarket API, Relayer).
- Enforce rate limits, price caps, and order validation.
- Produce audit logs for every state mutation.

## Frontend: Permitted Actions

- Display data received from backend via WebSocket or REST.
- Relay user actions (place order, cancel order, claim, adjust config) to backend endpoints.
- Format values for display (e.g., `0.85` to `85`).
- Show connection/health status as reported by backend.
- Store UI preferences (theme, layout) locally.

## Frontend: Prohibited Actions

- **No direct API calls** to Polymarket, RTDS, Relayer, or any external service.
- **No trading logic** -- no price comparisons, no order sizing, no rule evaluation.
- **No credential access** -- frontend never sees, stores, or transmits credentials.
- **No state derivation** -- frontend does not calculate PnL, position size, or balance.
- **No caching of authoritative data** -- frontend treats all backend-pushed data as ephemeral display values.
- **No autonomous actions** -- frontend never initiates actions without explicit user interaction.

## Enforcement

If the frontend requires data, it requests it from the backend. If the frontend needs an action performed, it sends a command to the backend. There are no exceptions.
