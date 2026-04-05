"""EligibilityGate — trade-eligible event filtreleme.

Trade-eligible olmayan event için:
- WS subscription açılmaz
- Evaluation yapılmaz
- Gereksiz kaynak tüketimi YOK

Eligible koşul:
- CoinSettings mevcut
- coin_enabled = True
- is_configured = True (tüm zorunlu alanlar doldurulmuş)
"""

import logging
from dataclasses import dataclass

from backend.settings.settings_store import SettingsStore
from backend.settings.coin_settings import CoinSettings
from backend.logging_config.service import get_logger, log_event

logger = get_logger("orchestrator.eligibility")


@dataclass
class EligibilityResult:
    """Eligibility filtreleme sonucu."""
    eligible: list[dict]     # trade-eligible event'ler
    ineligible: list[dict]   # eligible olmayan event'ler
    reasons: dict[str, str]  # coin → neden ineligible


class EligibilityGate:
    """Trade-eligible event filtreleyici.

    Discovery sonuçlarını alır, CoinSettings'e göre eligible/ineligible ayırır.
    """

    def __init__(self, store: SettingsStore):
        self._store = store

    def filter(self, discovered_events: list[dict]) -> EligibilityResult:
        """Discovery sonuçlarını eligible/ineligible olarak ayır.

        Args:
            discovered_events: Discovery'den gelen event listesi.
                Her event dict'inde 'asset' key'i olmalı.

        Returns:
            EligibilityResult with eligible/ineligible lists.
        """
        eligible = []
        ineligible = []
        reasons = {}

        for event in discovered_events:
            asset = self._extract_asset(event)
            if not asset:
                ineligible.append(event)
                reasons[str(event)] = "asset_unknown"
                continue

            settings = self._store.get(asset)

            if settings is None:
                ineligible.append(event)
                reasons[asset] = "no_settings"
                continue

            if not settings.coin_enabled:
                ineligible.append(event)
                reasons[asset] = "coin_disabled"
                continue

            if not settings.is_configured:
                ineligible.append(event)
                reasons[asset] = "config_incomplete"
                continue

            if not settings.is_trade_eligible:
                ineligible.append(event)
                reasons[asset] = "not_eligible"
                continue

            eligible.append(event)

        log_event(
            logger, logging.DEBUG,
            f"Eligibility: {len(eligible)} eligible, {len(ineligible)} ineligible",
            entity_type="orchestrator",
            entity_id="eligibility",
            payload={"eligible": len(eligible), "ineligible": len(ineligible)},
        )

        return EligibilityResult(
            eligible=eligible,
            ineligible=ineligible,
            reasons=reasons,
        )

    @staticmethod
    def _extract_asset(event: dict) -> str:
        """Event'ten asset adını çıkar."""
        # DiscoveredEvent veya raw dict
        if hasattr(event, 'asset'):
            return event.asset
        return event.get("asset", "")
