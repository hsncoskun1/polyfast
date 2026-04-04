"""Market mapping — event to token to market eşleşme katmanı.

Maps Polymarket events to their corresponding tokens and markets.
Each 5M Up/Down event has two outcomes (YES/NO) corresponding to
two tokens on two markets (UP side and DOWN side).

v0.3.1 scope: mapping contract only. No PTB, no prices, no snapshots.

Responsibilities:
- Map event condition_id to token IDs and market slugs
- Identify UP/DOWN sides
- Handle unmappable events explicitly (no silent failure)

Does NOT:
- Fetch PTB (→ v0.3.2)
- Normalize prices (→ v0.3.3)
- Produce backend snapshots (→ v0.3.5)
- Evaluate rules (→ v0.4.x)
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from backend.domain.startup_guard import HealthIncident, HealthSeverity
from backend.logging_config.service import get_logger, log_event

logger = get_logger("market_mapping")


class MarketSide(str, Enum):
    """Which side of the Up/Down market."""
    UP = "up"
    DOWN = "down"


class MappingStatus(str, Enum):
    """Result of a mapping attempt."""
    MAPPED = "mapped"
    UNMAPPABLE = "unmappable"
    ERROR = "error"


@dataclass(frozen=True)
class TokenMapping:
    """Single token mapping within a market.

    Attributes:
        token_id: Polymarket token identifier.
        side: UP or DOWN.
        outcome: Original outcome string (e.g., "Yes", "No").
    """
    token_id: str
    side: MarketSide
    outcome: str


@dataclass(frozen=True)
class MarketMap:
    """Complete mapping for a 5M Up/Down event.

    Attributes:
        condition_id: Event condition ID (key).
        asset: Crypto asset symbol.
        tokens: List of token mappings (typically 2: UP + DOWN).
        status: MAPPED or UNMAPPABLE.
        mapped_at: When mapping was created.
    """
    condition_id: str
    asset: str
    tokens: tuple[TokenMapping, ...]
    status: MappingStatus
    mapped_at: datetime

    def get_token_by_side(self, side: MarketSide) -> TokenMapping | None:
        """Get token mapping for a specific side."""
        for t in self.tokens:
            if t.side == side:
                return t
        return None

    @property
    def up_token(self) -> TokenMapping | None:
        return self.get_token_by_side(MarketSide.UP)

    @property
    def down_token(self) -> TokenMapping | None:
        return self.get_token_by_side(MarketSide.DOWN)

    @property
    def is_complete(self) -> bool:
        """True if both UP and DOWN tokens are mapped."""
        return self.up_token is not None and self.down_token is not None


class MarketMapper:
    """Maps events to their token/market structure.

    Takes raw event/market data and produces MarketMap objects.
    Failure is explicit — unmappable events are clearly marked.
    """

    def map_event(self, event_data: dict) -> MarketMap:
        """Map a single event to its market structure.

        Args:
            event_data: Raw event data from API containing tokens/markets.

        Returns:
            MarketMap with MAPPED or UNMAPPABLE status.
        """
        condition_id = str(event_data.get("conditionId", event_data.get("condition_id", "")))
        asset = self._extract_asset(event_data)

        if not condition_id:
            log_event(
                logger, logging.WARNING,
                "Event missing condition_id, cannot map",
                entity_type="mapping",
                entity_id="unmappable",
            )
            return MarketMap(
                condition_id="",
                asset=asset,
                tokens=(),
                status=MappingStatus.UNMAPPABLE,
                mapped_at=datetime.now(timezone.utc),
            )

        tokens = self._extract_tokens(event_data)

        if not tokens:
            log_event(
                logger, logging.WARNING,
                f"Event {condition_id} has no mappable tokens",
                entity_type="mapping",
                entity_id=condition_id,
            )
            return MarketMap(
                condition_id=condition_id,
                asset=asset,
                tokens=(),
                status=MappingStatus.UNMAPPABLE,
                mapped_at=datetime.now(timezone.utc),
            )

        log_event(
            logger, logging.INFO,
            f"Event mapped: {condition_id} ({asset}) — {len(tokens)} tokens",
            entity_type="mapping",
            entity_id=condition_id,
            payload={"asset": asset, "token_count": len(tokens)},
        )

        return MarketMap(
            condition_id=condition_id,
            asset=asset,
            tokens=tuple(tokens),
            status=MappingStatus.MAPPED,
            mapped_at=datetime.now(timezone.utc),
        )

    def _extract_tokens(self, event_data: dict) -> list[TokenMapping]:
        """Extract token mappings from event data.

        Polymarket events typically have 'tokens' array with
        token_id and outcome fields.
        """
        raw_tokens = event_data.get("tokens", [])
        if not raw_tokens:
            # Try markets → tokens nested structure
            markets = event_data.get("markets", [])
            for market in markets:
                raw_tokens.extend(market.get("tokens", []))

        mappings = []
        for token in raw_tokens:
            token_id = str(token.get("token_id", token.get("tokenId", "")))
            outcome = str(token.get("outcome", ""))

            if not token_id:
                continue

            side = self._classify_side(outcome)
            mappings.append(TokenMapping(
                token_id=token_id,
                side=side,
                outcome=outcome,
            ))

        return mappings

    def _classify_side(self, outcome: str) -> MarketSide:
        """Classify an outcome as UP or DOWN side.

        Convention:
        - "Yes" / first outcome → UP
        - "No" / second outcome → DOWN
        """
        lower = outcome.lower()
        if lower in ("yes", "up", "higher", "above"):
            return MarketSide.UP
        return MarketSide.DOWN

    def _extract_asset(self, event_data: dict) -> str:
        """Extract crypto asset from event data."""
        question = event_data.get("question", event_data.get("title", "")).upper()
        for asset in ["BTC", "ETH", "SOL", "DOGE", "XRP", "BNB", "MATIC", "LINK",
                       "ADA", "AVAX", "DOT", "SHIB", "LTC", "UNI", "ATOM"]:
            if asset in question:
                return asset
        return "UNKNOWN"
