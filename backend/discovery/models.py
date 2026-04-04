"""Discovery models — minimal event representation for discovery phase.

DiscoveredEvent is the raw output of discovery. It does NOT represent
registry state, live validation, or trading readiness.

Updated in v0.3.1-live: adapted to real Polymarket Gamma API response structure.
- Event title (not question) at event level
- Tags for category/duration (not keyword parsing)
- Slug contains asset and duration info
- Markets nested under events with conditionId, clobTokenIds, outcomes
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class DiscoveredEvent:
    """A Polymarket event discovered during scan.

    Attributes:
        condition_id: Polymarket condition ID (from market level).
        question: Event question/title.
        slug: URL slug for the event.
        asset: Crypto asset symbol (e.g., "BTC", "ETH").
        duration: Event duration string (e.g., "5m").
        category: Event category (e.g., "crypto").
        end_date: Event end timestamp (UTC).
        discovered_at: When this event was first seen by discovery.
        clob_token_ids: CLOB token IDs for UP/DOWN sides.
        outcomes: Outcome labels (e.g., ["Up", "Down"]).
    """
    condition_id: str
    question: str
    slug: str
    asset: str
    duration: str
    category: str
    end_date: datetime
    discovered_at: datetime
    clob_token_ids: tuple[str, ...] = ()
    outcomes: tuple[str, ...] = ()

    @classmethod
    def from_api_event(cls, event: dict) -> "DiscoveredEvent | None":
        """Create a DiscoveredEvent from Polymarket Gamma API event data.

        Handles the real Gamma API structure:
        - Event level: title, slug, tags, markets[]
        - Market level: conditionId, clobTokenIds, outcomes, question

        Returns None if the event cannot be parsed.
        """
        try:
            # Event-level fields
            title = event.get("title", "")
            slug = event.get("slug", "")
            tags = event.get("tags", [])

            # Extract from tags
            category = _extract_category_from_tags(tags)
            duration = _extract_duration_from_tags(tags)
            asset = _extract_asset_from_slug(slug, title)

            # End date from event level
            end_date_str = event.get("endDate", "")
            end_date = (
                datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                if end_date_str
                else datetime.now(timezone.utc)
            )

            # Market-level fields (first market)
            markets = event.get("markets", [])
            condition_id = ""
            clob_token_ids = ()
            outcomes = ()
            question = title  # fallback

            if markets:
                m = markets[0]
                condition_id = m.get("conditionId", "")
                question = m.get("question", title)

                # clobTokenIds can be JSON string or list
                raw_clob = m.get("clobTokenIds", [])
                if isinstance(raw_clob, str):
                    try:
                        raw_clob = json.loads(raw_clob)
                    except (json.JSONDecodeError, TypeError):
                        raw_clob = []
                clob_token_ids = tuple(str(t) for t in raw_clob) if raw_clob else ()

                # outcomes can be JSON string or list
                raw_outcomes = m.get("outcomes", [])
                if isinstance(raw_outcomes, str):
                    try:
                        raw_outcomes = json.loads(raw_outcomes)
                    except (json.JSONDecodeError, TypeError):
                        raw_outcomes = []
                outcomes = tuple(raw_outcomes) if raw_outcomes else ()

            if not condition_id:
                return None

            return cls(
                condition_id=condition_id,
                question=question,
                slug=slug,
                asset=asset,
                duration=duration,
                category=category,
                end_date=end_date,
                discovered_at=datetime.now(timezone.utc),
                clob_token_ids=clob_token_ids,
                outcomes=outcomes,
            )
        except Exception:
            return None


def _extract_category_from_tags(tags: list) -> str:
    """Extract category from Gamma API tags list."""
    if not tags:
        return "unknown"
    tag_slugs = set()
    for tag in tags:
        if isinstance(tag, dict):
            tag_slugs.add(tag.get("slug", "").lower())
        elif isinstance(tag, str):
            tag_slugs.add(tag.lower())

    if "crypto" in tag_slugs or "crypto-prices" in tag_slugs:
        return "crypto"
    return "unknown"


def _extract_duration_from_tags(tags: list) -> str:
    """Extract duration from Gamma API tags list."""
    if not tags:
        return "unknown"
    for tag in tags:
        slug = ""
        if isinstance(tag, dict):
            slug = tag.get("slug", "").lower()
        elif isinstance(tag, str):
            slug = tag.lower()

        if slug == "5m":
            return "5m"
        if slug == "15m":
            return "15m"
        if slug == "1h":
            return "1h"
        if slug == "4h":
            return "4h"
    return "unknown"


def _extract_asset_from_slug(slug: str, title: str) -> str:
    """Extract crypto asset from event slug or title.

    Gamma API slug format for 5M events: btc-updown-5m-TIMESTAMP
    """
    # Try slug first (most reliable for 5M events)
    slug_upper = slug.upper()
    for asset in ["BTC", "ETH", "SOL", "DOGE", "XRP", "BNB", "HYPE",
                   "ADA", "AVAX", "DOT", "SHIB", "LTC", "UNI", "ATOM"]:
        if slug_upper.startswith(asset + "-"):
            return asset

    # Fallback to title
    title_upper = title.upper()
    asset_map = {
        "BITCOIN": "BTC", "ETHEREUM": "ETH", "SOLANA": "SOL",
        "DOGECOIN": "DOGE", "HYPERLIQUID": "HYPE",
    }
    for name, symbol in asset_map.items():
        if name in title_upper:
            return symbol
    for asset in ["BTC", "ETH", "SOL", "DOGE", "XRP", "BNB"]:
        if asset in title_upper:
            return asset

    return "UNKNOWN"
