"""DiscoveryEngine — scans Polymarket for 5M Crypto Up/Down events.

This is the discovery skeleton (v0.2.3). It scans for candidate events
and classifies them. It does NOT manage registry state, live validation,
or market data.

Responsibilities:
- Query Polymarket API for events
- Filter: Crypto category, Up/Down subcategory, 5M duration
- Return list of DiscoveredEvent
- Report connectivity failures to health surface

Does NOT:
- Manage registry state (→ v0.2.4)
- Validate if events are actually live (→ v0.2.5)
- Fetch market data or PTB (→ v0.3.x)
- Evaluate rules (→ v0.4.x)
"""

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.auth_clients.public_client import PublicMarketClient
from backend.auth_clients.errors import ClientError
from backend.discovery.models import DiscoveredEvent
from backend.domain.startup_guard import HealthIncident, HealthSeverity
from backend.logging_config.service import get_logger, log_event

logger = get_logger("discovery")


@dataclass
class DiscoveryResult:
    """Result of a single discovery scan."""
    events: list[DiscoveredEvent] = field(default_factory=list)
    total_scanned: int = 0
    total_matched: int = 0
    parse_failures: int = 0
    success: bool = True
    error_message: str = ""
    health_incidents: list[HealthIncident] = field(default_factory=list)
    scanned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class DiscoveryEngine:
    """Scans Polymarket for 5M Crypto Up/Down events.

    Uses PublicMarketClient (no credentials needed) to query the
    Polymarket Gamma API for events matching the target criteria.
    """

    # Target filters — based on real Gamma API tag structure
    # Source: https://polymarket.com/crypto/5M
    # tag_slug=5M returns all 5M events (Up or Down format)
    TARGET_TAG_SLUG = "5M"
    TARGET_CATEGORY = "crypto"
    TARGET_DURATION = "5m"
    # Title format: "[Asset] Up or Down - [Date], [Time]-[Time] ET"
    TITLE_PATTERN = "up or down"

    def __init__(self, public_client: PublicMarketClient):
        self._client = public_client

    async def scan(self) -> DiscoveryResult:
        """Execute a discovery scan for 5M Crypto Up/Down events.

        Returns:
            DiscoveryResult with matched events or error details.
        """
        try:
            raw_events = await self._fetch_events()
        except ClientError as e:
            incident = HealthIncident(
                severity=HealthSeverity.WARNING,
                category="discovery",
                message=f"Discovery scan failed: {e}",
                suggested_action="Check network connectivity and Polymarket API availability.",
            )
            log_event(
                logger, logging.WARNING,
                f"Discovery scan failed: {e}",
                entity_type="discovery",
                entity_id="scan_failure",
                payload={"error_category": e.category.value, "source": e.source},
            )
            return DiscoveryResult(
                success=False,
                error_message=str(e),
                health_incidents=[incident],
            )
        except Exception as e:
            incident = HealthIncident(
                severity=HealthSeverity.WARNING,
                category="discovery",
                message=f"Discovery scan unexpected error: {e}",
                suggested_action="Check Polymarket API response format.",
            )
            log_event(
                logger, logging.ERROR,
                f"Discovery scan unexpected error: {e}",
                entity_type="discovery",
                entity_id="scan_failure",
            )
            return DiscoveryResult(
                success=False,
                error_message=f"Unexpected error: {e}",
                health_incidents=[incident],
            )

        # Parse and filter
        matched = []
        parse_failures = 0
        for raw in raw_events:
            event = DiscoveredEvent.from_api_event(raw)
            if event is None:
                parse_failures += 1
                log_event(
                    logger, logging.WARNING,
                    "Failed to parse event from API response",
                    entity_type="discovery",
                    entity_id="parse_failure",
                    payload={"raw_keys": list(raw.keys()) if isinstance(raw, dict) else "not_dict"},
                )
                continue
            if self._matches_criteria(event):
                matched.append(event)

        log_event(
            logger, logging.INFO,
            f"Discovery scan complete: {len(raw_events)} scanned, {len(matched)} matched, {parse_failures} parse failures",
            entity_type="discovery",
            entity_id="scan_complete",
            payload={
                "total_scanned": len(raw_events),
                "total_matched": len(matched),
                "parse_failures": parse_failures,
            },
        )

        return DiscoveryResult(
            events=matched,
            total_scanned=len(raw_events),
            total_matched=len(matched),
            parse_failures=parse_failures,
            success=True,
        )

    async def _fetch_events(self) -> list[dict]:
        """Fetch raw event data from Polymarket Gamma API.

        Uses tag_slug=up-or-down to get Up/Down events directly.
        This is the correct endpoint based on live API validation.

        Raises:
            ClientError: On API failure (classified by BaseClient).
        """
        response = await self._client.get("/events", params={
            "tag_slug": self.TARGET_TAG_SLUG,
            "closed": "false",
            "limit": "100",
        })
        data = response.json()

        # Gamma API returns list directly or nested
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return []

    def _matches_criteria(self, event: DiscoveredEvent) -> bool:
        """Check if an event matches 5M Crypto Up/Down criteria.

        Source: https://polymarket.com/crypto/5M
        Title format: "[Asset] Up or Down - [Date], [Time]-[Time] ET"
        Each 5M event has exactly 300 seconds duration.

        Filtering:
        - tag_slug=5M pre-filters at API level
        - Title must contain "Up or Down" (guards against non-updown 5M events)
        - Must be crypto category
        - Must be 5M duration
        """
        # Must be crypto
        if event.category != self.TARGET_CATEGORY:
            return False

        # Must be 5M duration
        if event.duration != self.TARGET_DURATION:
            return False

        # Title must match Up or Down pattern
        if self.TITLE_PATTERN not in event.question.lower():
            return False

        # Must be currently live or upcoming (within reasonable window)
        # Slug format: btc-updown-5m-TIMESTAMP where TIMESTAMP is event end time
        if not self._is_current_or_upcoming(event.slug):
            return False

        return True

    def _is_current_or_upcoming(self, slug: str, lookahead_seconds: int = 1800) -> bool:
        """Check if event is currently live or upcoming within lookahead window.

        Slug format: asset-updown-5m-TIMESTAMP
        TIMESTAMP = event START time (end_date = TIMESTAMP + 300).
        Each 5M event lasts exactly 300 seconds.

        Args:
            slug: Event slug containing timestamp.
            lookahead_seconds: How far ahead to look for upcoming events (default 30 min).
        """
        match = re.search(r'-(\d{10,})$', slug)
        if not match:
            return True

        event_start_ts = int(match.group(1))  # slug timestamp = START
        event_end_ts = event_start_ts + 300
        now = int(time.time())

        # Event is live if: start <= now < end
        # Event is upcoming if: now < start <= now + lookahead
        return event_start_ts <= now + lookahead_seconds and event_end_ts >= now
