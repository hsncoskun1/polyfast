"""Coin action API — toggle enable/disable.

POST /api/coin/{symbol}/toggle  → coin_enabled flip + persist

Action endpoint'leri read-only dashboard router'dan ayrı tutulur.
İleride explicit set, settings save gibi action'lar buraya eklenir.
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.logging_config.service import get_logger, log_event

logger = get_logger("api.coin")

router = APIRouter()


class CoinToggleResponse(BaseModel):
    """Toggle sonucu."""
    success: bool
    symbol: str
    enabled: bool   # toggle sonrası yeni değer
    message: str


def _get_orchestrator():
    """Orchestrator referansını al — main.py'deki global instance."""
    from backend.main import get_orchestrator
    return get_orchestrator()


@router.post("/coin/{symbol}/toggle", response_model=CoinToggleResponse)
async def coin_toggle(symbol: str):
    """Coin enabled/disabled toggle.

    - Settings'i olan coin'in coin_enabled field'ını flip eder
    - In-memory + SQLite persist (SettingsStore.set() → _persist())
    - Settings'i olmayan coin → 404
    - Açık pozisyona dokunmaz — sadece yeni entry aranıp aranmayacağını belirler
    """
    orch = _get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    symbol_upper = symbol.upper()
    result = orch.settings_store.toggle_coin(symbol_upper)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Coin ayarı bulunamadı: {symbol_upper}",
        )

    action = "etkinleştirildi" if result.coin_enabled else "devre dışı bırakıldı"
    log_event(
        logger, logging.INFO,
        f"Coin toggle: {symbol_upper} → {action}",
        entity_type="coin",
        entity_id=symbol_upper,
        payload={"enabled": result.coin_enabled},
    )

    return CoinToggleResponse(
        success=True,
        symbol=symbol_upper,
        enabled=result.coin_enabled,
        message=f"{symbol_upper} {action}",
    )
