"""Event cleanup — biten event'in pipeline/PTB/bridge verilerini temizler.

Expiration vs Cleanup ayrımı:
- EXPIRED = registry state geçişi (kayıt kalır, status değişir)
- Cleanup = artık tutulması gerekmeyen event VERİLERİNİ temizle

Cleanup kapsamı:
- LivePricePipeline → clear_event(condition_id)
- PTBFetcher → clear_event(condition_id)
- WSPriceBridge → unregister_token(token_id)

Cleanup YAPMAZ:
- CoinPriceClient → coin bazlı ortak veri, event bazlı değil
- Registry kaydı → silinmez, EXPIRED state'te kalır
"""

import logging

from backend.market_data.live_price import LivePricePipeline
from backend.market_data.ws_price_bridge import WSPriceBridge
from backend.ptb.fetcher import PTBFetcher
from backend.logging_config.service import get_logger, log_event

logger = get_logger("orchestrator.cleanup")


class EventCleanup:
    """Biten event'lerin pipeline verilerini temizler."""

    def __init__(
        self,
        pipeline: LivePricePipeline,
        ptb_fetcher: PTBFetcher,
        bridge: WSPriceBridge,
    ):
        self._pipeline = pipeline
        self._ptb = ptb_fetcher
        self._bridge = bridge
        self._cleaned_count: int = 0

    def cleanup_event(self, condition_id: str) -> None:
        """Tek event'in verilerini temizle.

        CoinPriceClient'a DOKUNMAZ — coin bazlı ortak veri.
        Registry kaydını SİLMEZ — EXPIRED state'te kalır.
        """
        # Pipeline record temizle
        self._pipeline.clear_event(condition_id)

        # PTB record temizle
        self._ptb.clear_event(condition_id)

        # Bridge token route'larını temizle (condition_id bazlı)
        tokens_to_remove = [
            tid for tid, route in self._bridge._token_routes.items()
            if route.condition_id == condition_id
        ]
        for tid in tokens_to_remove:
            self._bridge.unregister_token(tid)

        self._cleaned_count += 1

        log_event(
            logger, logging.INFO,
            f"Event cleanup: {condition_id} (tokens: {len(tokens_to_remove)})",
            entity_type="orchestrator",
            entity_id="cleanup",
        )

    def cleanup_expired_events(self, expired_condition_ids: list[str]) -> int:
        """Birden fazla expired event'i temizle.

        Returns:
            Temizlenen event sayısı.
        """
        for cid in expired_condition_ids:
            self.cleanup_event(cid)
        return len(expired_condition_ids)

    @property
    def total_cleaned(self) -> int:
        return self._cleaned_count
