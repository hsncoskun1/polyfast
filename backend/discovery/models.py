"""Discovery models — minimal event representation for discovery phase.

DiscoveredEvent is the raw output of discovery. It does NOT represent
registry state, live validation, or trading readiness. Those concerns
belong to later modules (registry v0.2.4, live validation v0.2.5).
"""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class DiscoveredEvent:
    """A Polymarket event discovered during scan.

    This is a discovery-phase model only. Registry state (active, expired,
    suspended, etc.) is NOT managed here.

    Attributes:
        condition_id: Polymarket condition ID (unique market identifier).
        question: Event question/title.
        slug: URL slug for the event.
        asset: Crypto asset symbol (e.g., "BTC", "ETH").
        duration: Event duration string (e.g., "5m").
        category: Event category (e.g., "crypto").
        end_date: Event end timestamp (UTC).
        discovered_at: When this event was first seen by discovery.
    """
    condition_id: str
    question: str
    slug: str
    asset: str
    duration: str
    category: str
    end_date: datetime
    discovered_at: datetime

    @classmethod
    def from_api_event(cls, event: dict) -> "DiscoveredEvent | None":
        """Create a DiscoveredEvent from Polymarket API event data.

        Returns None if the event cannot be parsed.
        """
        try:
            end_date_str = event.get("endDate") or event.get("end_date_iso", "")
            end_date = (
                datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                if end_date_str
                else datetime.now(timezone.utc)
            )

            return cls(
                condition_id=str(event.get("conditionId", event.get("condition_id", ""))),
                question=event.get("question", event.get("title", "")),
                slug=event.get("slug", ""),
                asset=_extract_asset(event),
                duration=_extract_duration(event),
                category=event.get("category", "").lower(),
                end_date=end_date,
                discovered_at=datetime.now(timezone.utc),
            )
        except Exception:
            return None


def _extract_asset(event: dict) -> str:
    """Extract the crypto asset symbol from event data."""
    question = event.get("question", event.get("title", "")).upper()
    # Common crypto assets on Polymarket 5M events
    for asset in ["BTC", "ETH", "SOL", "DOGE", "XRP", "BNB", "MATIC", "LINK",
                   "ADA", "AVAX", "DOT", "SHIB", "LTC", "UNI", "ATOM"]:
        if asset in question:
            return asset
    return "UNKNOWN"


def _extract_duration(event: dict) -> str:
    """Extract event duration from event data."""
    question = event.get("question", event.get("title", "")).lower()
    # Check for duration markers
    if "15 min" in question or "15-min" in question or "15m" in question:
        return "15m"
    if "5 min" in question or "5-min" in question or "5m" in question:
        return "5m"
    if "1 hour" in question or "1h" in question or "1-hour" in question:
        return "1h"
    if "4 hour" in question or "4h" in question or "4-hour" in question:
        return "4h"
    return "unknown"
