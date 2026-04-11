"""FeeRateFetcher — Polymarket CLOB API'den dinamik fee rate cekim.

Kurallar:
- Real mode: fee rate cekilemezse order GONDERILMEZ
- Paper mode: cekilemezse default guard kullanilabilir
- fee_rate hardcode EDILMEZ — her zaman dinamik cekilmeli
- SDK payload fee handling ile bot accounting AYRI — ikisi ayni sey degil

Kaynak: CLOB API neg_risk_fee_rate veya fee_rate_bps
"""

import logging
from datetime import datetime, timezone

import httpx

from backend.logging_config.service import get_logger, log_event

logger = get_logger("execution.fee_rate")

# Polymarket crypto 5M: base_fee=1000 bps = 0.10
DEFAULT_CRYPTO_FEE_RATE = 0.10
CLOB_BASE_URL = "https://clob.polymarket.com"


class FeeRateFetcher:
    """Dinamik fee rate cekim.

    Real mode: cekilemezse None doner — order gonderilmez.
    Paper mode: cekilemezse default guard kullanilir.
    """

    def __init__(self, clob_url: str | None = None):
        self._clob_url = clob_url or CLOB_BASE_URL
        self._last_rate: float | None = None
        self._last_fetched_at: datetime | None = None
        self._fetch_count: int = 0
        self._fail_count: int = 0

    async def fetch_fee_rate(self, token_id: str) -> float | None:
        """CLOB API'den fee rate cek.

        Args:
            token_id: Market token ID (fee rate market'e gore degisebilir)

        Returns:
            Fee rate (0.072 gibi) veya None (cekilemedi)
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # CLOB neg_risk endpoint'inden fee rate
                resp = await client.get(
                    f"{self._clob_url}/neg-risk/markets/{token_id}",
                )
                if resp.status_code == 200:
                    data = resp.json()
                    # neg_risk_fee_rate veya fee_rate_bps alanlarini ara
                    rate = data.get("neg_risk_fee_rate")
                    if rate is None:
                        bps = data.get("fee_rate_bps")
                        if bps is not None:
                            rate = int(bps) / 10000.0

                    if rate is not None and rate > 0:
                        self._last_rate = float(rate)
                        self._last_fetched_at = datetime.now(timezone.utc)
                        self._fetch_count += 1
                        return self._last_rate

                # Fallback: genel market endpoint
                resp2 = await client.get(
                    f"{self._clob_url}/markets/{token_id}",
                )
                if resp2.status_code == 200:
                    data2 = resp2.json()
                    rate2 = data2.get("fee_rate_bps")
                    if rate2 is not None:
                        self._last_rate = int(rate2) / 10000.0
                        self._last_fetched_at = datetime.now(timezone.utc)
                        self._fetch_count += 1
                        return self._last_rate

        except Exception as e:
            self._fail_count += 1
            log_event(
                logger, logging.WARNING,
                f"Fee rate fetch failed: {e}",
                entity_type="execution",
                entity_id="fee_rate_error",
            )

        self._fail_count += 1
        return None

    def get_default_rate(self) -> float:
        """Paper mode icin default guard rate."""
        return DEFAULT_CRYPTO_FEE_RATE

    @property
    def last_rate(self) -> float | None:
        return self._last_rate

    @property
    def fetch_count(self) -> int:
        return self._fetch_count

    @property
    def fail_count(self) -> int:
        return self._fail_count
