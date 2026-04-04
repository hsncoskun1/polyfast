"""SSR PTB adapter — fetches PTB from Polymarket event page.

Uses ?__nextDataReq=1 parameter to get server-rendered page data,
then parses the priceToBeat field via regex.

FIELD NAME: priceToBeat (NOT openPrice)
- openPrice exists only for BTC in crypto-prices query
- priceToBeat exists for ALL 7 assets (BTC, ETH, SOL, XRP, DOGE, BNB, HYPE)
- priceToBeat matches the "Price To Beat" shown on Polymarket UI

ENDPOINT: https://polymarket.com/event/{slug}?__nextDataReq=1
- Works with httpx (no headless browser needed)
- Response ~2MB per asset
- Average fetch time ~0.4s per asset

KNOWN RISKS:
- priceToBeat field name may change without notice
- ?__nextDataReq=1 parameter may be removed by Polymarket
- Response size is large (~2MB) but fetch speed is acceptable
"""

import logging
import re
from datetime import datetime, timezone

import httpx

from backend.ptb.source_adapter import PTBSourceAdapter, PTBFetchResult
from backend.logging_config.service import get_logger, log_event

logger = get_logger("ptb.ssr_adapter")

EVENT_PAGE_URL = "https://polymarket.com/event/{slug}"


class SSRPTBAdapter(PTBSourceAdapter):
    """Fetches PTB from Polymarket event page via ?__nextDataReq=1.

    Parses the priceToBeat field from the server-rendered response.
    Works for all 7 assets (BTC, ETH, SOL, XRP, DOGE, BNB, HYPE).
    No headless browser required.
    """

    def __init__(self, timeout_seconds: float = 15.0):
        self._timeout = timeout_seconds

    @property
    def source_name(self) -> str:
        return "ssr_price_to_beat"

    async def fetch_ptb(self, asset: str, event_slug: str) -> PTBFetchResult:
        """Fetch PTB (priceToBeat) from event page.

        Args:
            asset: Crypto asset symbol (e.g., "BTC").
            event_slug: Event slug (e.g., "btc-updown-5m-1775293800").

        Returns:
            PTBFetchResult with priceToBeat value or error.
        """
        url = f"{EVENT_PAGE_URL.format(slug=event_slug)}?__nextDataReq=1"

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=True,
            ) as client:
                response = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0",
                })

            if response.status_code != 200:
                return PTBFetchResult(
                    success=False,
                    value=None,
                    source_name=self.source_name,
                    fetched_at=datetime.now(timezone.utc),
                    error=f"HTTP {response.status_code} from event page",
                )

            return self._parse_ptb(response.text, asset, event_slug)

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

    def _parse_ptb(
        self, html: str, asset: str, event_slug: str
    ) -> PTBFetchResult:
        """Parse priceToBeat from server response.

        Uses regex to find the priceToBeat field in the HTML/JSON response.
        This field exists for all 7 supported assets.
        """
        now = datetime.now(timezone.utc)

        # Primary: priceToBeat field (works for ALL assets)
        match = re.search(r'"priceToBeat"\s*:\s*"?([0-9.]+)"?', html)
        if match:
            ptb_value = float(match.group(1))
            log_event(
                logger, logging.INFO,
                f"PTB acquired: {asset} = {ptb_value}",
                entity_type="ptb",
                entity_id=event_slug,
                payload={"ptb_value": ptb_value, "source": self.source_name},
            )
            return PTBFetchResult(
                success=True,
                value=ptb_value,
                source_name=self.source_name,
                fetched_at=now,
            )

        # Fallback: openPrice field (BTC only, legacy)
        match_open = re.search(r'"openPrice"\s*:\s*([0-9.]+)', html)
        if match_open:
            ptb_value = float(match_open.group(1))
            log_event(
                logger, logging.INFO,
                f"PTB acquired via openPrice fallback: {asset} = {ptb_value}",
                entity_type="ptb",
                entity_id=event_slug,
                payload={"ptb_value": ptb_value, "source": f"{self.source_name}_openPrice_fallback"},
            )
            return PTBFetchResult(
                success=True,
                value=ptb_value,
                source_name=f"{self.source_name}_openPrice_fallback",
                fetched_at=now,
            )

        log_event(
            logger, logging.WARNING,
            f"priceToBeat not found in response for {event_slug}",
            entity_type="ptb",
            entity_id=event_slug,
        )
        return PTBFetchResult(
            success=False,
            value=None,
            source_name=self.source_name,
            fetched_at=now,
            error="priceToBeat field not found in response",
        )
