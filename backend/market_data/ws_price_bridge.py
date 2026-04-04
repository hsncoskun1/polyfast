"""WSPriceBridge — connects RTDSClient message flow to LivePricePipeline.

Receives parsed WS messages from RTDSClient, extracts price data,
and routes to LivePricePipeline.update_from_ws() with correct
condition_id, asset, and side mapping.

v0.3.4 scope: WS → Pipeline integration, token routing, stale detection.

Responsibilities:
- Register as RTDSClient message callback
- Parse WS market messages (best_bid, best_ask per token)
- Map token_id → (condition_id, asset, side) via token registry
- Forward to LivePricePipeline.update_from_ws()
- Track per-token last message time for stale detection
- Surface health incidents when WS goes stale

Does NOT:
- Manage WS connection (→ RTDSClient)
- Normalize prices (→ LivePricePipeline)
- Map events to tokens (→ MarketMapper, called externally to register)
- Produce snapshots (→ v0.3.5)
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from backend.domain.startup_guard import HealthIncident, HealthSeverity
from backend.logging_config.service import get_logger, log_event
from backend.market_data.live_price import LivePricePipeline

logger = get_logger("market_data.ws_bridge")


@dataclass
class TokenRoute:
    """Routing info for a single token from WS to pipeline."""
    token_id: str
    condition_id: str
    asset: str
    side: str  # "up" or "down"


class WSPriceBridge:
    """Routes RTDS WebSocket messages to LivePricePipeline.

    Usage:
        bridge = WSPriceBridge(pipeline)
        bridge.register_token("token123", "cond456", "BTC", "up")
        rtds_client.set_message_callback(bridge.on_ws_message)
    """

    def __init__(self, pipeline: LivePricePipeline):
        self._pipeline = pipeline
        # token_id → TokenRoute
        self._token_routes: dict[str, TokenRoute] = {}
        # token_id → last message datetime
        self._last_message_at: dict[str, datetime] = {}
        self._total_routed: int = 0
        self._total_skipped: int = 0

    # ─── Token Registration ───

    def register_token(
        self,
        token_id: str,
        condition_id: str,
        asset: str,
        side: str,
    ) -> None:
        """Register a token for routing.

        Args:
            token_id: CLOB token ID (from WS subscription).
            condition_id: Event condition ID (pipeline key).
            asset: Crypto asset symbol.
            side: "up" or "down".
        """
        self._token_routes[token_id] = TokenRoute(
            token_id=token_id,
            condition_id=condition_id,
            asset=asset,
            side=side,
        )

    def unregister_token(self, token_id: str) -> None:
        """Remove a token from routing."""
        self._token_routes.pop(token_id, None)
        self._last_message_at.pop(token_id, None)

    def clear_all(self) -> None:
        """Clear all token routes."""
        self._token_routes.clear()
        self._last_message_at.clear()

    @property
    def registered_token_ids(self) -> list[str]:
        """All registered token IDs (for WS subscription)."""
        return list(self._token_routes.keys())

    @property
    def registered_count(self) -> int:
        return len(self._token_routes)

    @property
    def total_routed(self) -> int:
        return self._total_routed

    @property
    def total_skipped(self) -> int:
        return self._total_skipped

    # ─── WS Message Handling ───

    def on_ws_message(self, data: dict[str, Any]) -> None:
        """Process a single WS message from RTDSClient.

        Expected WS message formats from Polymarket RTDS:

        Market event (price_change):
        [
            {
                "asset_id": "token_id_here",
                "event_type": "price_change",
                "price": "0.55",
                ...
            }
        ]

        Or book event (best_bid_ask):
        [
            {
                "asset_id": "token_id_here",
                "event_type": "best_bid_ask" | "book",
                "best_bid": "0.55",
                "best_ask": "0.56",
                ...
            }
        ]

        Also handles single-object messages (not wrapped in array).
        """
        # WS can send array of events or single event
        if isinstance(data, list):
            for item in data:
                self._process_single_event(item)
        elif isinstance(data, dict):
            self._process_single_event(data)

    def _process_single_event(self, event: dict[str, Any]) -> None:
        """Process a single market event from WS."""
        asset_id = event.get("asset_id", "")

        if not asset_id:
            return

        # Check if we're tracking this token
        route = self._token_routes.get(asset_id)
        if route is None:
            self._total_skipped += 1
            return

        # Extract price data
        best_bid, best_ask = self._extract_prices(event)

        if best_bid is None or best_ask is None:
            return

        # Route to pipeline
        self._pipeline.update_from_ws(
            condition_id=route.condition_id,
            asset=route.asset,
            side=route.side,
            best_bid=best_bid,
            best_ask=best_ask,
        )

        self._last_message_at[asset_id] = datetime.now(timezone.utc)
        self._total_routed += 1

    @staticmethod
    def _extract_prices(event: dict[str, Any]) -> tuple[float | None, float | None]:
        """Extract best_bid and best_ask from a WS event.

        Handles multiple message formats:
        - best_bid_ask event: has best_bid/best_ask fields
        - price_change event: has price field (use as bid, ask = bid)
        - book event: has bids/asks arrays
        """
        event_type = event.get("event_type", "")

        # Format 1: best_bid / best_ask fields (most common from market subscription)
        if "best_bid" in event and "best_ask" in event:
            try:
                bid = float(event["best_bid"])
                ask = float(event["best_ask"])
                return bid, ask
            except (ValueError, TypeError):
                return None, None

        # Format 2: price field (price_change events)
        if "price" in event:
            try:
                price = float(event["price"])
                return price, price
            except (ValueError, TypeError):
                return None, None

        # Format 3: changes array with price/side
        changes = event.get("changes", [])
        if changes:
            try:
                # Take last change as current
                last = changes[-1]
                if isinstance(last, dict):
                    price = float(last.get("price", 0))
                    return price, price
            except (ValueError, TypeError, IndexError):
                pass

        return None, None

    # ─── Health ───

    def get_health_incidents(self) -> list[HealthIncident]:
        """Get health incidents for unresponsive tokens."""
        incidents = []
        now = datetime.now(timezone.utc)

        for token_id, route in self._token_routes.items():
            last = self._last_message_at.get(token_id)
            if last is None:
                # Never received data for this token
                incidents.append(HealthIncident(
                    severity=HealthSeverity.WARNING,
                    category="market_data",
                    message=f"No WS data received for {route.asset} ({route.side}) token",
                    suggested_action="Check WS subscription and token ID.",
                ))
            else:
                age = (now - last).total_seconds()
                if age > 60:  # No update for 60s on a streaming feed
                    incidents.append(HealthIncident(
                        severity=HealthSeverity.WARNING,
                        category="market_data",
                        message=f"WS data stale for {route.asset} ({route.side}): {age:.0f}s",
                        suggested_action="Check RTDS connection health.",
                    ))

        return incidents
