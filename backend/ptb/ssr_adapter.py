"""SSR PTB adapter — fetches PTB from Polymarket event page.

Uses ?__nextDataReq=1 parameter to get server-rendered page data,
then parses the live event's PTB from the response.

PTB = Price To Beat = event açılışındaki coin'in USD fiyatı (Chainlink source).
PTB bir outcome fiyatı (0.52) DEĞİLDİR — gerçek USD coin fiyatıdır.
Örnekler: BTC=$67,260.12, ETH=$2,062.70, DOGE=$0.092177

DOĞRU PATTERN:
  "openPrice":VALUE,"closePrice":null
  → closePrice:null = event hâlâ canlı (kapanmamış)
  → Response'ta sadece 1 adet olur (canlı event)
  → Geçmiş eventlerin hepsinde closePrice dolu olur

ENDPOINT: https://polymarket.com/event/{slug}?__nextDataReq=1
- Works with httpx (no headless browser needed)
- Response ~2MB per asset
- Average fetch time ~0.4s per asset

ÖNEMLİ:
- Slug live event'e ait olmalı (geçmiş veya upcoming değil)
- Live event slug hesabı: slot_start = (now // 300) * 300
  slug = {asset}-updown-5m-{slot_start}
- PTB event başladıktan 1-2 dakika sonra set edilebilir
- Event canlı değilse veya PTB henüz set edilmemişse None döner
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

    PTB = coin'in event açılışındaki USD fiyatı (Chainlink source).
    Örnekler: BTC=$67,260.12, ETH=$2,062.70, DOGE=$0.092177

    Doğru pattern: "openPrice":VALUE,"closePrice":null
    closePrice:null = event hâlâ canlı → sadece 1 adet olur response'ta.
    """

    def __init__(self, timeout_seconds: float = 15.0):
        self._timeout = timeout_seconds

    @property
    def source_name(self) -> str:
        return "ssr_open_price"

    async def fetch_ptb(self, asset: str, event_slug: str) -> PTBFetchResult:
        """Fetch PTB (openPrice) from live event page.

        Args:
            asset: Crypto asset symbol (e.g., "BTC").
            event_slug: Live event slug (e.g., "btc-updown-5m-1775334300").

        Returns:
            PTBFetchResult with USD coin price or error.
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
        """Parse live event PTB from server response.

        Primary pattern: "openPrice":VALUE,"closePrice":null
        - closePrice:null guarantees this is the LIVE event (not historical)
        - Only 1 match exists in the response (verified)
        - Returns USD coin price (e.g., 67260.12 for BTC)
        """
        now = datetime.now(timezone.utc)

        # Primary: openPrice with closePrice:null = live event PTB
        match = re.search(
            r'"openPrice":([0-9.]+),"closePrice":null',
            html,
        )
        if match:
            ptb_value = float(match.group(1))
            log_event(
                logger, logging.INFO,
                f"PTB acquired: {asset} = ${ptb_value}",
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

        # PTB not found — event may not have started yet or PTB not set
        log_event(
            logger, logging.WARNING,
            f"PTB not found for {event_slug} — event may not be live yet",
            entity_type="ptb",
            entity_id=event_slug,
        )
        return PTBFetchResult(
            success=False,
            value=None,
            source_name=self.source_name,
            fetched_at=now,
            error="openPrice with closePrice:null not found — event may not be live or PTB not yet set",
        )
