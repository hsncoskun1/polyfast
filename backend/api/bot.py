"""Bot lifecycle API — start / pause / stop.

POST /api/bot/start   → trading başlat (paused ise resume)
POST /api/bot/pause   → yeni entry durdur, exit monitoring devam
POST /api/bot/stop    → graceful shutdown, tüm loop'lar durur
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.logging_config.service import get_logger, log_event

logger = get_logger("api.bot")

router = APIRouter()


class BotActionResponse(BaseModel):
    """Bot action sonucu."""
    success: bool
    state: str  # "running" | "paused" | "stopped"
    message: str


def _get_orchestrator():
    """Orchestrator referansını al — main.py'deki global instance."""
    from backend.main import get_orchestrator
    return get_orchestrator()


def _current_state(orch) -> str:
    """Orchestrator'ın mevcut lifecycle state'ini döndür."""
    if not orch.trading_enabled:
        return "stopped"
    if orch.paused:
        return "paused"
    return "running"


@router.post("/bot/start", response_model=BotActionResponse)
async def bot_start():
    """Bot'u başlat veya resume et.

    - Stopped ise: tüm loop'lar yeniden başlatılır
    - Paused ise: paused=False → entry üretimi devam eder
    - Running ise: no-op (idempotent)
    """
    orch = _get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    prev = _current_state(orch)

    if prev == "running":
        return BotActionResponse(
            success=True,
            state="running",
            message="Bot zaten çalışıyor",
        )

    if prev == "paused":
        orch.resume()
        log_event(logger, logging.INFO, "Bot resumed (paused → running)",
                  entity_type="bot", entity_id="lifecycle")
        return BotActionResponse(
            success=True,
            state="running",
            message="Bot devam ediyor",
        )

    # stopped → start
    try:
        await orch.start()
        log_event(logger, logging.INFO, "Bot started (stopped → running)",
                  entity_type="bot", entity_id="lifecycle")
        return BotActionResponse(
            success=True,
            state="running",
            message="Bot başlatıldı",
        )
    except Exception as e:
        log_event(logger, logging.ERROR, f"Bot start failed: {e}",
                  entity_type="bot", entity_id="lifecycle_error")
        raise HTTPException(status_code=500, detail=f"Start failed: {e}")


@router.post("/bot/pause", response_model=BotActionResponse)
async def bot_pause():
    """Bot'u duraklat.

    - Yeni entry/order üretimi durur
    - Exit monitoring (TP/SL/FS) DEVAM EDER — açık pozisyonlar korunur
    - Running ise: paused=True
    - Paused ise: no-op
    - Stopped ise: hata (önce start gerekli)
    """
    orch = _get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    prev = _current_state(orch)

    if prev == "stopped":
        raise HTTPException(
            status_code=409,
            detail="Bot durmuş durumda — önce başlatın",
        )

    if prev == "paused":
        return BotActionResponse(
            success=True,
            state="paused",
            message="Bot zaten duraklatılmış",
        )

    # running → paused
    orch.pause()
    log_event(logger, logging.INFO, "Bot paused (running → paused)",
              entity_type="bot", entity_id="lifecycle")
    return BotActionResponse(
        success=True,
        state="paused",
        message="Bot duraklatıldı — exit monitoring devam ediyor",
    )


@router.post("/bot/stop", response_model=BotActionResponse)
async def bot_stop():
    """Bot'u durdur (graceful shutdown).

    - Tüm loop'lar durur
    - State flush yapılır (SQLite'a kaydedilir)
    - Stopped ise: no-op
    """
    orch = _get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    prev = _current_state(orch)

    if prev == "stopped":
        return BotActionResponse(
            success=True,
            state="stopped",
            message="Bot zaten durmuş",
        )

    try:
        await orch.stop()
        log_event(logger, logging.INFO, f"Bot stopped ({prev} → stopped)",
                  entity_type="bot", entity_id="lifecycle")
        return BotActionResponse(
            success=True,
            state="stopped",
            message="Bot durduruldu — state kaydedildi",
        )
    except Exception as e:
        log_event(logger, logging.ERROR, f"Bot stop failed: {e}",
                  entity_type="bot", entity_id="lifecycle_error")
        raise HTTPException(status_code=500, detail=f"Stop failed: {e}")
