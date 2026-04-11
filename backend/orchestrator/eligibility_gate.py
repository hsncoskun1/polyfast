"""EligibilityGate — trade-eligible event filtreleme.

Trade-eligible olmayan event için:
- WS subscription açılmaz
- Evaluation yapılmaz
- Gereksiz kaynak tüketimi YOK

Eligible koşul:
- Trading credential'lar mevcut (API key + secret + passphrase)
- CoinSettings mevcut
- coin_enabled = True
- is_configured = True (tüm zorunlu alanlar doldurulmuş)
"""

import logging
from dataclasses import dataclass
from typing import Optional

from backend.settings.settings_store import SettingsStore
from backend.settings.coin_settings import CoinSettings
from backend.auth_clients.credential_store import CredentialStore
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

    Discovery sonuçlarını alır, credential + CoinSettings'e göre
    eligible/ineligible ayırır.

    Credential gate: trading credential yoksa hiçbir coin eligible olamaz.
    Bu kontrol coin bazlı kontrollerden ÖNCE çalışır.
    Paper mode'da credential gate bypass edilir — credential olmadan da
    evaluation yapılabilir.
    """

    def __init__(
        self,
        store: SettingsStore,
        credential_store: Optional[CredentialStore] = None,
        paper_mode: bool = False,
    ):
        self._store = store
        self._credential_store = credential_store
        self._paper_mode = paper_mode

    def filter(self, discovered_events: list[dict]) -> EligibilityResult:
        """Discovery sonuçlarını eligible/ineligible olarak ayır.

        Args:
            discovered_events: Discovery'den gelen event listesi.
                Her event dict'inde 'asset' key'i olmalı.

        Returns:
            EligibilityResult with eligible/ineligible lists.
        """
        # Credential gate — trading credential yoksa tüm coinler ineligible
        # Paper mode'da credential gerekmez — bypass
        if self._credential_store is not None and not self._paper_mode:
            if not self._credential_store.credentials.has_trading_credentials():
                reasons = {}
                for event in discovered_events:
                    asset = self._extract_asset(event) or str(event)
                    reasons[asset] = "no_credentials"
                log_event(
                    logger, logging.WARNING,
                    "Credential gate: trading credentials eksik — tüm coinler ineligible",
                    entity_type="orchestrator",
                    entity_id="eligibility",
                    payload={"reason": "no_credentials", "count": len(discovered_events)},
                )
                return EligibilityResult(
                    eligible=[],
                    ineligible=list(discovered_events),
                    reasons=reasons,
                )

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
