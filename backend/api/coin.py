"""Coin action API — toggle + settings read/save.

POST /api/coin/{symbol}/toggle    → coin_enabled flip + persist
GET  /api/coin/{symbol}/settings  → mevcut ayarlar + governance oku
POST /api/coin/{symbol}/settings  → kural parametreleri kaydet + persist

Action endpoint'leri read-only dashboard router'dan ayrı tutulur.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from backend.logging_config.service import get_logger, log_event
from backend.settings.coin_settings import SideMode

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


# ╔══════════════════════════════════════════════════════════════╗
# ║  Settings save                                                ║
# ╚══════════════════════════════════════════════════════════════╝

class CoinSettingsRequest(BaseModel):
    """Coin kural parametreleri — endpoint seviyesinde validation.

    coin_enabled bu model'de YOK — toggle ayrı endpoint.
    Tüm alanlar optional (partial update).
    """
    side_mode: Optional[str] = None
    delta_threshold: Optional[float] = None
    price_min: Optional[int] = None
    price_max: Optional[int] = None
    spread_max: Optional[float] = None
    time_min: Optional[int] = None
    time_max: Optional[int] = None
    event_max: Optional[int] = None
    order_amount: Optional[float] = None
    reactivate_on_return: Optional[bool] = None

    @field_validator('side_mode')
    @classmethod
    def validate_side_mode(cls, v):
        if v is not None:
            valid = [m.value for m in SideMode]
            if v not in valid:
                raise ValueError(f"Geçersiz side_mode: {v}. Geçerli: {valid}")
        return v

    @field_validator('delta_threshold', 'spread_max', 'order_amount')
    @classmethod
    def validate_positive_float(cls, v):
        if v is not None and v < 0:
            raise ValueError("Negatif değer kabul edilmez")
        return v

    @field_validator('price_min', 'price_max', 'time_min', 'time_max', 'event_max')
    @classmethod
    def validate_non_negative_int(cls, v):
        if v is not None and v < 0:
            raise ValueError("Negatif değer kabul edilmez")
        return v


class CoinSettingsResponse(BaseModel):
    """Settings save sonucu."""
    success: bool
    symbol: str
    configured: bool
    message: str
    missing_fields: list[str] = []


# ╔══════════════════════════════════════════════════════════════╗
# ║  Field governance — backend authority                        ║
# ╚══════════════════════════════════════════════════════════════╝

class FieldPolicy(BaseModel):
    """Tek bir alan için governance policy."""
    visible: bool = True
    editable: bool = True
    locked: bool = False


# Default governance — spread locked, diğerleri açık
DEFAULT_FIELD_GOVERNANCE: dict[str, dict] = {
    "side_mode":        {"visible": True, "editable": True, "locked": False},
    "delta_threshold":  {"visible": True, "editable": True, "locked": False},
    "price_min":        {"visible": True, "editable": True, "locked": False},
    "price_max":        {"visible": True, "editable": True, "locked": False},
    "time_min":         {"visible": True, "editable": True, "locked": False},
    "time_max":         {"visible": True, "editable": True, "locked": False},
    "event_max":        {"visible": True, "editable": True, "locked": False},
    "order_amount":     {"visible": True, "editable": True, "locked": False},
    "spread_max":       {"visible": True, "editable": False, "locked": True},
}


class CoinSettingsReadResponse(BaseModel):
    """Coin ayarları okuma — mevcut değerler + governance."""
    symbol: str
    configured: bool
    coin_enabled: bool
    missing_fields: list[str]
    settings: dict              # alan adı → değer
    field_governance: dict      # alan adı → {visible, editable, locked}


def _check_missing_fields(settings) -> list[str]:
    """Configured olmak için eksik alanları bul.

    spread_max dahil DEĞİL — governance locked/kapalı.
    side_mode dahil DEĞİL — default DOMINANT_ONLY (her zaman geçerli).
    """
    missing = []
    if settings.delta_threshold <= 0:
        missing.append('delta_threshold')
    if settings.price_min <= 0:
        missing.append('price_min')
    if settings.price_max <= 0:
        missing.append('price_max')
    if settings.price_min >= settings.price_max and settings.price_min > 0:
        missing.append('price_min < price_max')
    if settings.time_min <= 0:
        missing.append('time_min')
    if settings.time_max <= 0:
        missing.append('time_max')
    if settings.time_min >= settings.time_max and settings.time_min > 0:
        missing.append('time_min < time_max')
    if settings.order_amount <= 0:
        missing.append('order_amount')
    return missing


@router.get("/coin/{symbol}/settings", response_model=CoinSettingsReadResponse)
async def coin_settings_read(symbol: str):
    """Coin ayarlarını oku — mevcut değerler + governance.

    Frontend modal açılınca mevcut ayarları doldurur.
    Governance bilgisi ile hangi alanın editable/locked olduğunu bildirir.
    """
    orch = _get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    symbol_upper = symbol.upper()
    cs = orch.settings_store.get(symbol_upper)

    if cs is None:
        # Coin ayarı yok — boş default döndür
        from backend.settings.coin_settings import CoinSettings
        cs = CoinSettings(coin=symbol_upper)

    missing = _check_missing_fields(cs)

    return CoinSettingsReadResponse(
        symbol=symbol_upper,
        configured=cs.is_configured,
        coin_enabled=cs.coin_enabled,
        missing_fields=missing,
        settings={
            "side_mode": cs.side_mode.value,
            "delta_threshold": cs.delta_threshold,
            "price_min": cs.price_min,
            "price_max": cs.price_max,
            "time_min": cs.time_min,
            "time_max": cs.time_max,
            "event_max": cs.event_max,
            "order_amount": cs.order_amount,
            "spread_max": cs.spread_max,
        },
        field_governance=DEFAULT_FIELD_GOVERNANCE,
    )


@router.post("/coin/{symbol}/settings", response_model=CoinSettingsResponse)
async def coin_settings_save(symbol: str, body: CoinSettingsRequest):
    """Coin kural parametrelerini kaydet.

    - Partial update: sadece gönderilen field'lar güncellenir
    - coin_enabled DEĞİŞMEZ — toggle ayrı endpoint
    - Coin yoksa yeni oluşturur (coin_enabled=false)
    - Persist: SettingsStore.set() → _persist() → SQLite
    - Validation: min/max ilişkileri, negatif değerler, enum
    """
    orch = _get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    symbol_upper = symbol.upper()

    # Body'den sadece set edilmiş (None olmayan) field'ları al
    fields = {k: v for k, v in body.model_dump().items() if v is not None}

    # side_mode string → SideMode enum dönüşümü
    if 'side_mode' in fields:
        fields['side_mode'] = SideMode(fields['side_mode'])

    # Cross-field validation: price_min < price_max
    existing = orch.settings_store.get(symbol_upper)
    p_min = fields.get('price_min', existing.price_min if existing else 0)
    p_max = fields.get('price_max', existing.price_max if existing else 0)
    if p_min > 0 and p_max > 0 and p_min >= p_max:
        raise HTTPException(status_code=422, detail="price_min, price_max'tan küçük olmalı")

    # Cross-field validation: time_min < time_max
    t_min = fields.get('time_min', existing.time_min if existing else 0)
    t_max = fields.get('time_max', existing.time_max if existing else 0)
    if t_min > 0 and t_max > 0 and t_min >= t_max:
        raise HTTPException(status_code=422, detail="time_min, time_max'tan küçük olmalı")

    result = orch.settings_store.update_settings(symbol_upper, **fields)

    missing = _check_missing_fields(result)
    configured = result.is_configured

    log_event(
        logger, logging.INFO,
        f"Coin settings saved: {symbol_upper} (configured={configured})",
        entity_type="coin",
        entity_id=symbol_upper,
        payload={"configured": configured, "fields_updated": list(fields.keys())},
    )

    msg = f"{symbol_upper} ayarları kaydedildi"
    if not configured:
        msg += f" — {len(missing)} eksik alan var"

    return CoinSettingsResponse(
        success=True,
        symbol=symbol_upper,
        configured=configured,
        message=msg,
        missing_fields=missing,
    )
