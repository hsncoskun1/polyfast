"""Live price pipeline — normalize, timestamp, freshness, invalid data filtering.

Processes raw price data from RTDS/Gamma into normalized LivePriceRecord.
Tracks freshness and filters invalid values before they reach evaluation.

CRITICAL RULES (from CLAUDE.md):
- Invalid data (0, --, empty) MUST NOT reach evaluation layer
- Stale data must be marked, not silently used
- Price source must be visible

This module does NOT:
- Produce backend snapshots (→ v0.3.5)
- Evaluate rules (→ v0.4.x)
- Execute trades (→ v0.5.x)
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from backend.domain.startup_guard import HealthIncident, HealthSeverity
from backend.logging_config.service import get_logger, log_event

logger = get_logger("market_data.live_price")

# Default stale threshold — price older than this is considered stale
DEFAULT_STALE_THRESHOLD_SEC = 30


class PriceStatus(str, Enum):
    """Status of a live price reading."""
    FRESH = "fresh"         # Recently updated, valid
    STALE = "stale"         # Not updated within threshold
    INVALID = "invalid"     # Data is invalid (0, empty, malformed)
    WAITING = "waiting"     # No price received yet


@dataclass
class LivePriceRecord:
    """Normalized live price record for a single event/market.

    Attributes:
        condition_id: Market condition ID.
        asset: Crypto asset symbol.
        up_price: Up outcome price (0.0-1.0 range).
        down_price: Down outcome price (0.0-1.0 range).
        spread: Difference between best ask and best bid.
        status: Current price status.
        updated_at: When this price was last updated (UTC).
        source: Where this price came from.
        stale_threshold_sec: Seconds before price is considered stale.
    """
    condition_id: str
    asset: str
    up_price: float = 0.0
    down_price: float = 0.0
    spread: float = 0.0
    status: PriceStatus = PriceStatus.WAITING
    updated_at: datetime | None = None
    source: str = ""
    stale_threshold_sec: int = DEFAULT_STALE_THRESHOLD_SEC

    @property
    def is_fresh(self) -> bool:
        if self.status == PriceStatus.INVALID or self.updated_at is None:
            return False
        age = (datetime.now(timezone.utc) - self.updated_at).total_seconds()
        return age <= self.stale_threshold_sec

    @property
    def is_stale(self) -> bool:
        if self.updated_at is None:
            return False
        age = (datetime.now(timezone.utc) - self.updated_at).total_seconds()
        return age > self.stale_threshold_sec

    @property
    def is_valid(self) -> bool:
        return self.status in (PriceStatus.FRESH, PriceStatus.STALE)

    @property
    def age_seconds(self) -> float | None:
        if self.updated_at is None:
            return None
        return (datetime.now(timezone.utc) - self.updated_at).total_seconds()

    def check_freshness(self) -> None:
        """Update status based on current freshness."""
        if self.status == PriceStatus.INVALID or self.status == PriceStatus.WAITING:
            return
        if self.is_stale:
            self.status = PriceStatus.STALE


class LivePricePipeline:
    """Normalizes and manages live price data for all tracked markets.

    Responsibilities:
    - Parse raw price data from Gamma API outcomePrices
    - Normalize to LivePriceRecord
    - Track freshness per market
    - Filter invalid data (0, empty, malformed)
    - Surface stale/invalid state

    Does NOT:
    - Fetch data (caller provides raw data)
    - Produce snapshots
    - Evaluate rules
    """

    def __init__(self, stale_threshold_sec: int = DEFAULT_STALE_THRESHOLD_SEC):
        self._records: dict[str, LivePriceRecord] = {}
        self._stale_threshold = stale_threshold_sec

    def update_from_gamma(
        self,
        condition_id: str,
        asset: str,
        outcome_prices_raw: str | list,
        spread: float = 0.0,
    ) -> LivePriceRecord:
        """Update price from Gamma API outcomePrices field.

        Args:
            condition_id: Market condition ID.
            asset: Crypto asset symbol.
            outcome_prices_raw: outcomePrices as JSON string or list.
            spread: Market spread value.

        Returns:
            Updated LivePriceRecord.
        """
        record = self._get_or_create(condition_id, asset)

        # Parse outcomePrices
        prices = self._parse_outcome_prices(outcome_prices_raw)

        if prices is None:
            record.status = PriceStatus.INVALID
            log_event(
                logger, logging.WARNING,
                f"Invalid outcomePrices for {asset}: {outcome_prices_raw}",
                entity_type="live_price",
                entity_id=condition_id,
            )
            return record

        up_price, down_price = prices

        # Validate values
        if not self._is_valid_price(up_price) or not self._is_valid_price(down_price):
            record.status = PriceStatus.INVALID
            log_event(
                logger, logging.WARNING,
                f"Invalid price values for {asset}: up={up_price} down={down_price}",
                entity_type="live_price",
                entity_id=condition_id,
            )
            return record

        # Update record
        record.up_price = up_price
        record.down_price = down_price
        record.spread = spread
        record.status = PriceStatus.FRESH
        record.updated_at = datetime.now(timezone.utc)
        record.source = "gamma_outcome_prices"

        return record

    def get_record(self, condition_id: str) -> LivePriceRecord | None:
        """Get price record, with freshness check."""
        record = self._records.get(condition_id)
        if record:
            record.check_freshness()
        return record

    def get_all_records(self) -> list[LivePriceRecord]:
        """Get all records with freshness check."""
        for r in self._records.values():
            r.check_freshness()
        return list(self._records.values())

    def clear_event(self, condition_id: str) -> None:
        """Remove price record for an event (cleanup)."""
        self._records.pop(condition_id, None)

    def get_health_incidents(self) -> list[HealthIncident]:
        """Get health incidents for stale/invalid prices."""
        incidents = []
        for r in self._records.values():
            r.check_freshness()
            if r.status == PriceStatus.STALE:
                incidents.append(HealthIncident(
                    severity=HealthSeverity.WARNING,
                    category="market_data",
                    message=f"Stale price for {r.asset} (age: {r.age_seconds:.0f}s)",
                    suggested_action="Check RTDS connection and data feed.",
                ))
            elif r.status == PriceStatus.INVALID:
                incidents.append(HealthIncident(
                    severity=HealthSeverity.WARNING,
                    category="market_data",
                    message=f"Invalid price data for {r.asset}",
                    suggested_action="Check data source response format.",
                ))
        return incidents

    @property
    def fresh_count(self) -> int:
        return sum(1 for r in self._records.values() if r.is_fresh)

    @property
    def stale_count(self) -> int:
        return sum(1 for r in self._records.values() if r.is_stale)

    @property
    def invalid_count(self) -> int:
        return sum(1 for r in self._records.values() if r.status == PriceStatus.INVALID)

    def _get_or_create(self, condition_id: str, asset: str) -> LivePriceRecord:
        if condition_id not in self._records:
            self._records[condition_id] = LivePriceRecord(
                condition_id=condition_id,
                asset=asset,
                stale_threshold_sec=self._stale_threshold,
            )
        return self._records[condition_id]

    @staticmethod
    def _parse_outcome_prices(raw: str | list) -> tuple[float, float] | None:
        """Parse outcomePrices into (up_price, down_price).

        Handles JSON string or list format.
        Returns None if parsing fails.
        """
        try:
            if isinstance(raw, str):
                parsed = json.loads(raw)
            else:
                parsed = raw

            if not isinstance(parsed, list) or len(parsed) < 2:
                return None

            up = float(parsed[0])
            down = float(parsed[1])
            return (up, down)
        except (json.JSONDecodeError, ValueError, TypeError, IndexError):
            return None

    @staticmethod
    def _is_valid_price(price: float) -> bool:
        """Check if a price value is valid (not zero, not negative, within range)."""
        return 0.0 < price <= 1.0
