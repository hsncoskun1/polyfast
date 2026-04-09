"""Health check endpoint — system liveness and bot status contract.

v0.8.0-backend-contract: BotStatusContract frontend HealthIndicator/BotModeChip
icin eklendi. Frontend `snap.derivedHealth` / `snap.derivedLatencyMs` alanlari
dogrudan `bot_status` uzerinden beslenir.

Placeholder-first:
- `bot_status` alani eklendi, field'lar optional.
- Orchestrator hazir degilse (veya field henuz wired degilse) default (None) doner.
- Frontend null-safe tuketir, eksik field'lar icin default'lara duser.
"""

from typing import Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from backend.version import __version__

router = APIRouter()


HealthLiteral = Literal["healthy", "degraded", "critical", "unknown"]


class BotStatusContract(BaseModel):
    """Bot lifecycle + health contract.

    Tum alanlar OPTIONAL — placeholder-first. Orchestrator henuz her alani
    surmuyorsa None doner, frontend default'a duser.

    Kaynaklar (gelecekteki wiring):
      running               → Orchestrator.trading_enabled / running state
      health                → HealthAggregator.overall_status
      restore_phase         → Orchestrator.restore_phase
      shutdown_in_progress  → Orchestrator.shutdown_flag
      startup_guard_blocked → StartupGuard.blocked
      paused                → Orchestrator.paused
      uptime_sec            → backend.main.get_uptime()
      latency_ms            → RTDS WS ping metrik
      paper_mode            → Orchestrator.paper_mode
    """

    running: Optional[bool] = None
    health: Optional[HealthLiteral] = None
    restore_phase: Optional[bool] = None
    shutdown_in_progress: Optional[bool] = None
    startup_guard_blocked: Optional[bool] = None
    paused: Optional[bool] = None
    uptime_sec: Optional[int] = None
    latency_ms: Optional[int] = None
    paper_mode: Optional[bool] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    components: dict[str, str]

    # v0.8.0-backend-contract:
    bot_status: Optional[BotStatusContract] = None


def _build_bot_status(uptime_sec: float) -> BotStatusContract:
    """Build BotStatusContract from orchestrator state (placeholder-safe).

    Orchestrator runtime'a dokunmaz; sadece mevcut state'i okur.
    Eksik surucu (null orchestrator, henuz baglanmamis field) = None field.
    """
    try:
        from backend.main import get_orchestrator

        orch = get_orchestrator()
    except Exception:
        orch = None

    # Orchestrator yoksa: tum field'lar None, sadece uptime_sec dolu
    if orch is None:
        return BotStatusContract(
            running=False,
            health="unknown",
            uptime_sec=int(uptime_sec),
        )

    # Orchestrator var: her field'i defensive get ile oku
    running = getattr(orch, "trading_enabled", None)
    restore_phase = getattr(orch, "restore_phase", None)
    shutdown_in_progress = getattr(orch, "shutdown_flag", None)
    paused = getattr(orch, "paused", None)
    paper_mode = getattr(orch, "paper_mode", None)

    # Health: healthy default, orchestrator degraded flag varsa onu kullan
    degraded = getattr(orch, "degraded_mode", False)
    health: HealthLiteral = "degraded" if degraded else "healthy"

    # Startup guard
    startup_guard = getattr(orch, "startup_guard", None)
    startup_guard_blocked = None
    if startup_guard is not None:
        startup_guard_blocked = getattr(startup_guard, "blocked", None)

    return BotStatusContract(
        running=running,
        health=health,
        restore_phase=restore_phase,
        shutdown_in_progress=shutdown_in_progress,
        startup_guard_blocked=startup_guard_blocked,
        paused=paused,
        uptime_sec=int(uptime_sec),
        latency_ms=None,  # WS latency metrik sonraki adimda
        paper_mode=paper_mode,
    )


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return current system health status + bot lifecycle contract."""
    from backend.main import get_uptime

    uptime = get_uptime()

    return HealthResponse(
        status="ok",
        version=__version__,
        uptime_seconds=round(uptime, 2),
        components={},
        bot_status=_build_bot_status(uptime),
    )
