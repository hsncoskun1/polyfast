"""Global settings API — exit policy + system workflow.

GET  /api/settings/global  → mevcut global ayarları oku
POST /api/settings/global  → partial update + runtime yansıma

Coin-level ayarlar burada YOK — onlar /api/coin/{symbol}/settings'te.
sl_jump_threshold read-only — POST'ta ignore edilir.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.logging_config.service import get_logger, log_event

logger = get_logger("api.settings")

router = APIRouter()


# ╔══════════════════════════════════════════════════════════════╗
# ║  Models                                                       ║
# ╚══════════════════════════════════════════════════════════════╝

class GlobalSettingsResponse(BaseModel):
    """Global settings okuma response'u."""
    auto_start_bot_on_startup: bool
    bot_max_positions: int
    block_new_entries_when_claim_pending: bool
    tp_percentage: float
    tp_reevaluate: bool
    sl_enabled: bool
    sl_percentage: float
    sl_jump_threshold: float       # read-only
    fs_time_enabled: bool
    fs_time_seconds: int
    fs_pnl_enabled: bool
    fs_pnl_pct: float


class GlobalSettingsUpdateRequest(BaseModel):
    """Global settings partial update. None = değişmez."""
    auto_start_bot_on_startup: Optional[bool] = None
    bot_max_positions: Optional[int] = None
    block_new_entries_when_claim_pending: Optional[bool] = None
    tp_percentage: Optional[float] = None
    tp_reevaluate: Optional[bool] = None
    sl_enabled: Optional[bool] = None
    sl_percentage: Optional[float] = None
    # sl_jump_threshold: YOK — read-only, body'de gelse ignore
    fs_time_enabled: Optional[bool] = None
    fs_time_seconds: Optional[int] = None
    fs_pnl_enabled: Optional[bool] = None
    fs_pnl_pct: Optional[float] = None


class GlobalSettingsUpdateResponse(BaseModel):
    """Update sonucu."""
    success: bool
    message: str
    has_open_positions: bool


# ╔══════════════════════════════════════════════════════════════╗
# ║  Helpers                                                      ║
# ╚══════════════════════════════════════════════════════════════╝

def _get_orchestrator():
    from backend.main import get_orchestrator
    return get_orchestrator()


def _read_global_settings(orch) -> GlobalSettingsResponse:
    """Mevcut config'ten global settings oku."""
    cfg = orch._config
    tp = cfg.trading.exit_rules.take_profit
    sl = cfg.trading.exit_rules.stop_loss
    fs = cfg.trading.exit_rules.force_sell

    return GlobalSettingsResponse(
        auto_start_bot_on_startup=cfg.trading.auto_start_bot_on_startup,
        bot_max_positions=cfg.trading.entry_rules.bot_max.max_positions,
        block_new_entries_when_claim_pending=cfg.trading.claim.wait_for_claim_before_new_trade,
        tp_percentage=tp.percentage,
        tp_reevaluate=tp.reevaluate_on_retry,
        sl_enabled=sl.enabled,
        sl_percentage=sl.percentage,
        sl_jump_threshold=sl.jump_threshold,
        fs_time_enabled=fs.time.enabled,
        fs_time_seconds=fs.time.remaining_seconds,
        fs_pnl_enabled=fs.pnl_loss.enabled,
        fs_pnl_pct=fs.pnl_loss.loss_percentage,
    )


# ╔══════════════════════════════════════════════════════════════╗
# ║  Endpoints                                                    ║
# ╚══════════════════════════════════════════════════════════════╝

@router.get("/settings/global", response_model=GlobalSettingsResponse)
async def global_settings_read():
    """Global settings oku — exit policy + workflow."""
    orch = _get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    return _read_global_settings(orch)


@router.post("/settings/global", response_model=GlobalSettingsUpdateResponse)
async def global_settings_update(body: GlobalSettingsUpdateRequest):
    """Global settings güncelle — partial update + runtime yansıma.

    sl_jump_threshold read-only — body'de gelse ignore edilir.
    Değişiklikler ExitEvaluator/EvaluationLoop'a anında yansır.
    """
    orch = _get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    cfg = orch._config
    changed = []

    # ── auto_start ──
    if body.auto_start_bot_on_startup is not None:
        cfg.trading.auto_start_bot_on_startup = body.auto_start_bot_on_startup
        changed.append("auto_start_bot_on_startup")

    # ── bot_max_positions ──
    if body.bot_max_positions is not None:
        cfg.trading.entry_rules.bot_max.max_positions = body.bot_max_positions
        orch.evaluation_loop._bot_max_positions = body.bot_max_positions
        changed.append("bot_max_positions")

    # ── claim policy ──
    if body.block_new_entries_when_claim_pending is not None:
        cfg.trading.claim.wait_for_claim_before_new_trade = body.block_new_entries_when_claim_pending
        changed.append("block_new_entries_when_claim_pending")

    # ── TP ──
    if body.tp_percentage is not None:
        cfg.trading.exit_rules.take_profit.percentage = body.tp_percentage
        orch.exit_evaluator._tp_pct = body.tp_percentage
        changed.append("tp_percentage")

    if body.tp_reevaluate is not None:
        cfg.trading.exit_rules.take_profit.reevaluate_on_retry = body.tp_reevaluate
        orch.exit_evaluator._tp_reevaluate = body.tp_reevaluate
        changed.append("tp_reevaluate")

    # ── SL ──
    if body.sl_enabled is not None:
        cfg.trading.exit_rules.stop_loss.enabled = body.sl_enabled
        orch.exit_evaluator._sl_enabled = body.sl_enabled
        changed.append("sl_enabled")

    if body.sl_percentage is not None:
        cfg.trading.exit_rules.stop_loss.percentage = body.sl_percentage
        orch.exit_evaluator._sl_pct = body.sl_percentage
        changed.append("sl_percentage")

    # sl_jump_threshold: IGNORE — read-only

    # ── Force Sell Time ──
    if body.fs_time_enabled is not None:
        cfg.trading.exit_rules.force_sell.time.enabled = body.fs_time_enabled
        orch.exit_evaluator._fs_time_enabled = body.fs_time_enabled
        changed.append("fs_time_enabled")

    if body.fs_time_seconds is not None:
        cfg.trading.exit_rules.force_sell.time.remaining_seconds = body.fs_time_seconds
        orch.exit_evaluator._fs_time_seconds = body.fs_time_seconds
        changed.append("fs_time_seconds")

    # ── Force Sell PnL ──
    if body.fs_pnl_enabled is not None:
        cfg.trading.exit_rules.force_sell.pnl_loss.enabled = body.fs_pnl_enabled
        orch.exit_evaluator._fs_pnl_enabled = body.fs_pnl_enabled
        changed.append("fs_pnl_enabled")

    if body.fs_pnl_pct is not None:
        cfg.trading.exit_rules.force_sell.pnl_loss.loss_percentage = body.fs_pnl_pct
        orch.exit_evaluator._fs_pnl_pct = body.fs_pnl_pct
        changed.append("fs_pnl_pct")

    # Açık pozisyon kontrolü
    has_open = orch.position_tracker.open_position_count > 0 if hasattr(orch, 'position_tracker') else False

    if changed:
        log_event(
            logger, logging.INFO,
            f"Global settings updated: {', '.join(changed)}",
            entity_type="settings",
            entity_id="global",
            payload={"changed": changed, "has_open_positions": has_open},
        )

    msg = f"{len(changed)} ayar güncellendi" if changed else "Değişiklik yok"

    return GlobalSettingsUpdateResponse(
        success=True,
        message=msg,
        has_open_positions=has_open,
    )
