"""SSR PTB adapter — fetches PTB from Polymarket event page __NEXT_DATA__.

This adapter parses the server-side rendered HTML of a Polymarket event page
to extract the openPrice from the crypto-prices query in __NEXT_DATA__.

KNOWN LIMITATIONS:
- No public API endpoint exists for PTB (openPrice)
- Requires fetching full HTML page (~2MB)
- __NEXT_DATA__ structure may change without notice
- Build ID / query key format may change
- This is a maintenance risk — documented intentionally

SOURCE: __NEXT_DATA__ → crypto-prices query → {"openPrice": X, "closePrice": null}
VERIFIED: openPrice matches "Price To Beat" displayed on Polymarket page
"""

import json
import logging
import re
from datetime import datetime, timezone

import httpx

from backend.ptb.source_adapter import PTBSourceAdapter, PTBFetchResult
from backend.logging_config.service import get_logger, log_event

logger = get_logger("ptb.ssr_adapter")

# Polymarket event page URL pattern
EVENT_PAGE_URL = "https://polymarket.com/event/{slug}"


class SSRPTBAdapter(PTBSourceAdapter):
    """Fetches PTB from Polymarket event page SSR (__NEXT_DATA__).

    Parses the crypto-prices query from __NEXT_DATA__ script tag.
    Falls back to past-results if crypto-prices is not available.
    """

    def __init__(self, timeout_seconds: float = 15.0):
        self._timeout = timeout_seconds

    @property
    def source_name(self) -> str:
        return "ssr_next_data"

    async def fetch_ptb(self, asset: str, event_slug: str) -> PTBFetchResult:
        """Fetch PTB from event page __NEXT_DATA__.

        Args:
            asset: Crypto asset symbol (e.g., "BTC").
            event_slug: Event slug (e.g., "btc-updown-5m-1775293800").

        Returns:
            PTBFetchResult with openPrice or error.
        """
        url = EVENT_PAGE_URL.format(slug=event_slug)

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"},
            ) as client:
                response = await client.get(url)

            if response.status_code != 200:
                return PTBFetchResult(
                    success=False,
                    value=None,
                    source_name=self.source_name,
                    fetched_at=datetime.now(timezone.utc),
                    error=f"HTTP {response.status_code} from event page",
                )

            return self._parse_ptb_from_html(response.text, asset, event_slug)

        except httpx.TimeoutException:
            log_event(
                logger, logging.WARNING,
                f"PTB fetch timeout for {event_slug}",
                entity_type="ptb",
                entity_id=event_slug,
            )
            return PTBFetchResult(
                success=False,
                value=None,
                source_name=self.source_name,
                fetched_at=datetime.now(timezone.utc),
                error=f"Timeout after {self._timeout}s",
            )

        except Exception as e:
            log_event(
                logger, logging.WARNING,
                f"PTB fetch error for {event_slug}: {e}",
                entity_type="ptb",
                entity_id=event_slug,
            )
            return PTBFetchResult(
                success=False,
                value=None,
                source_name=self.source_name,
                fetched_at=datetime.now(timezone.utc),
                error=str(e),
            )

    def _parse_ptb_from_html(
        self, html: str, asset: str, event_slug: str
    ) -> PTBFetchResult:
        """Parse openPrice from __NEXT_DATA__ in HTML.

        Looks for crypto-prices query first, then past-results fallback.
        """
        now = datetime.now(timezone.utc)

        # Extract __NEXT_DATA__ JSON
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )

        if not match:
            log_event(
                logger, logging.WARNING,
                f"__NEXT_DATA__ not found in event page for {event_slug}",
                entity_type="ptb",
                entity_id=event_slug,
            )
            return PTBFetchResult(
                success=False,
                value=None,
                source_name=self.source_name,
                fetched_at=now,
                error="__NEXT_DATA__ script tag not found in HTML",
            )

        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError as e:
            return PTBFetchResult(
                success=False,
                value=None,
                source_name=self.source_name,
                fetched_at=now,
                error=f"Failed to parse __NEXT_DATA__ JSON: {e}",
            )

        queries = (
            data.get("props", {})
            .get("pageProps", {})
            .get("dehydratedState", {})
            .get("queries", [])
        )

        # Strategy 1: crypto-prices query (primary)
        for q in queries:
            key = q.get("queryKey", [])
            key_str = str(key)
            if "crypto-prices" in key_str and "price" in key_str:
                qdata = q.get("state", {}).get("data", {})
                if isinstance(qdata, dict) and "openPrice" in qdata:
                    open_price = qdata["openPrice"]
                    if open_price is not None:
                        log_event(
                            logger, logging.INFO,
                            f"PTB acquired via crypto-prices: {asset} = {open_price}",
                            entity_type="ptb",
                            entity_id=event_slug,
                        )
                        return PTBFetchResult(
                            success=True,
                            value=float(open_price),
                            source_name=self.source_name,
                            fetched_at=now,
                        )

        # Strategy 2: past-results fallback (last event's closePrice = current openPrice hypothesis)
        # NOT guaranteed to match — documented as fallback
        for q in queries:
            key = q.get("queryKey", [])
            key_str = str(key)
            if "past-results" in key_str:
                qdata = q.get("state", {}).get("data", {})
                results = qdata.get("data", {}).get("results", []) if isinstance(qdata, dict) else []
                if results:
                    last_result = results[-1]
                    open_price = last_result.get("openPrice")
                    if open_price is not None:
                        log_event(
                            logger, logging.INFO,
                            f"PTB acquired via past-results fallback: {asset} = {open_price}",
                            entity_type="ptb",
                            entity_id=event_slug,
                            payload={"fallback": True},
                        )
                        return PTBFetchResult(
                            success=True,
                            value=float(open_price),
                            source_name=f"{self.source_name}_past_results_fallback",
                            fetched_at=now,
                        )

        return PTBFetchResult(
            success=False,
            value=None,
            source_name=self.source_name,
            fetched_at=now,
            error="openPrice not found in __NEXT_DATA__ queries",
        )
