"""SubscriptionManager — eligible event'ler için WS subscribe/unsubscribe.

Eligible → subscribe:
- CLOB WS'e token subscribe (outcome fiyat)
- CoinPriceClient'a coin ekle (coin USD)
- PTB fetch başlat

Ineligible / expired → unsubscribe:
- CLOB WS'ten token unsubscribe
- CoinPriceClient'tan coin çıkar
- Cleanup

Diff hesabı:
- Önceki eligible set ile yeni eligible set karşılaştırılır
- Yeni eklenen → subscribe
- Çıkan → unsubscribe
- Değişmeyen → dokunma
"""

import logging
from dataclasses import dataclass, field

from backend.market_data.ws_price_bridge import WSPriceBridge
from backend.market_data.coin_price_client import CoinPriceClient
from backend.ptb.fetcher import PTBFetcher
from backend.logging_config.service import get_logger, log_event

logger = get_logger("orchestrator.subscription")


@dataclass
class SubscriptionDiff:
    """Subscribe/unsubscribe diff sonucu."""
    to_subscribe: list[str] = field(default_factory=list)    # yeni eligible asset'ler
    to_unsubscribe: list[str] = field(default_factory=list)  # artık eligible olmayan asset'ler
    unchanged: list[str] = field(default_factory=list)       # değişmeyen asset'ler


class SubscriptionManager:
    """Eligible event'lerin WS subscription'larını yönetir.

    Discovery → eligibility → subscription diff → subscribe/unsubscribe.
    """

    def __init__(
        self,
        bridge: WSPriceBridge,
        coin_price_client: CoinPriceClient,
        ptb_fetcher: PTBFetcher,
        rtds_client=None,
    ):
        self._bridge = bridge
        self._coin_client = coin_price_client
        self._ptb_fetcher = ptb_fetcher
        self._rtds_client = rtds_client
        # CURRENT SLOT OWNERSHIP: her asset icin tek aktif trade event
        # asset -> condition_id (su an aktif olan event)
        self._active_events: dict[str, str] = {}

    @property
    def _current_subscribed(self) -> set[str]:
        """Geriye uyum: subscribe olan asset set'i."""
        return set(self._active_events.keys())

    def compute_diff(self, new_eligible_assets: list[str]) -> SubscriptionDiff:
        """Asset bazli diff hesapla."""
        new_set = set(a.upper() for a in new_eligible_assets)
        old_set = set(self._active_events.keys())

        return SubscriptionDiff(
            to_subscribe=sorted(new_set - old_set),
            to_unsubscribe=sorted(old_set - new_set),
            unchanged=sorted(new_set & old_set),
        )

    async def apply_diff(
        self,
        diff: SubscriptionDiff,
        event_map: dict[str, dict],
    ) -> None:
        """Diff uygula + condition_id degisim tespiti.

        CURRENT SLOT OWNERSHIP:
        - Yeni asset → subscribe (bridge register + RTDS)
        - Kaldirilan asset → unsubscribe (bridge unregister)
        - Ayni asset, FARKLI condition_id → ROTATE (eski unregister, yeni register)
        """
        changed = False

        # 1. Yeni asset'ler
        for asset in diff.to_subscribe:
            event_data = event_map.get(asset, {})
            await self._subscribe_asset(asset, event_data)
            self._active_events[asset] = event_data.get("condition_id", "")
            changed = True

        # 2. Kaldirilan asset'ler
        for asset in diff.to_unsubscribe:
            self._unsubscribe_asset(asset)
            self._active_events.pop(asset, None)
            changed = True

        # 3. Unchanged asset'ler — CONDITION_ID DEGISTI MI?
        for asset in diff.unchanged:
            event_data = event_map.get(asset, {})
            new_cid = event_data.get("condition_id", "")
            old_cid = self._active_events.get(asset, "")

            if new_cid and old_cid and new_cid != old_cid:
                # ROTATE: ayni asset, yeni slot event
                self._unsubscribe_asset(asset)
                await self._subscribe_asset(asset, event_data)
                self._active_events[asset] = new_cid
                changed = True
                log_event(
                    logger, logging.INFO,
                    f"Event rotated: {asset} cid={old_cid[:12]}→{new_cid[:12]}",
                    entity_type="orchestrator",
                    entity_id=f"rotate_{asset}",
                )

        # 4. RTDS WS resubscribe — bridge'deki guncel token set
        if changed and self._rtds_client:
            all_tokens = self._bridge.registered_token_ids
            self._rtds_client.update_subscription(all_tokens)
            if self._rtds_client.is_connected:
                try:
                    await self._rtds_client.subscribe(all_tokens)
                except Exception as e:
                    log_event(
                        logger, logging.WARNING,
                        f"RTDS subscribe failed: {e}",
                        entity_type="orchestrator",
                        entity_id="rtds_subscribe_error",
                    )

        if changed:
            log_event(
                logger, logging.INFO,
                f"Subscription updated: {len(self._active_events)} assets, "
                f"+{len(diff.to_subscribe)} -{len(diff.to_unsubscribe)}",
                entity_type="orchestrator",
                entity_id="subscription_diff",
            )

    async def _subscribe_asset(self, asset: str, event_data: dict) -> None:
        """Tek asset için subscribe: CLOB WS + coin USD + PTB."""
        condition_id = event_data.get("condition_id", "")
        token_ids = event_data.get("token_ids", [])
        slug = event_data.get("slug", "")
        sides = event_data.get("sides", [])

        # Bridge'e token route ekle
        for i, token_id in enumerate(token_ids):
            side = sides[i] if i < len(sides) else "up"
            self._bridge.register_token(token_id, condition_id, asset, side)

        # CoinPriceClient'a coin ekle
        current_coins = list(self._coin_client._coins)
        if asset.upper() not in [c.upper() for c in current_coins]:
            current_coins.append(asset.upper())
            self._coin_client.set_coins(current_coins)

        log_event(
            logger, logging.INFO,
            f"Subscribed: {asset} (tokens: {len(token_ids)})",
            entity_type="orchestrator",
            entity_id=f"subscribe_{asset}",
        )

    def _unsubscribe_asset(self, asset: str) -> None:
        """Tek asset için unsubscribe: cleanup."""
        # Bridge'den token route'ları kaldır
        token_ids_to_remove = [
            tid for tid, route in self._bridge._token_routes.items()
            if route.asset.upper() == asset.upper()
        ]
        for tid in token_ids_to_remove:
            self._bridge.unregister_token(tid)

        # PTB cleanup
        # (condition_id lazım — şimdilik log only)

        log_event(
            logger, logging.INFO,
            f"Unsubscribed: {asset}",
            entity_type="orchestrator",
            entity_id=f"unsubscribe_{asset}",
        )

    @property
    def subscribed_assets(self) -> set[str]:
        return set(self._current_subscribed)

    @property
    def subscribed_count(self) -> int:
        return len(self._current_subscribed)
