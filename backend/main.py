"""Polyfast Backend — FastAPI Application Entry Point.

Lifespan manages the Orchestrator which starts all loops:
- DiscoveryLoop: slot-aware bul-ve-bekle
- CoinPriceClient: batch poll loop (~600ms/cycle)
- EvaluationLoop: periyodik rule evaluation

Order gönderme YOK — sadece sinyal üretimi (Faz 5).
"""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.health import router as health_router
from backend.api.dashboard import router as dashboard_router
from backend.api.bot import router as bot_router
from backend.api.coin import router as coin_router
from backend.api.credential import router as credential_router
from backend.api.settings import router as settings_router
from backend.version import __version__
from backend.orchestrator.wiring import Orchestrator
from backend.logging_config.service import get_logger, log_event

import logging

logger = get_logger("main")

_start_time: float = 0.0
_orchestrator: Orchestrator | None = None


def get_uptime() -> float:
    """Return seconds since application start."""
    return time.time() - _start_time


def get_orchestrator() -> Orchestrator | None:
    """Get the running orchestrator instance."""
    return _orchestrator


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown.

    Starts Orchestrator which manages all loops.
    Gracefully stops on shutdown.
    """
    global _start_time, _orchestrator
    _start_time = time.time()

    log_event(
        logger, logging.INFO,
        f"Polyfast v{__version__} starting",
        entity_type="app",
        entity_id="startup",
    )

    # ── Database init + migrations ──
    from backend.persistence.database import init_db, close_db
    from backend.persistence.migrations import run_migrations
    db = await init_db()
    applied = await run_migrations(db)
    if applied:
        log_event(
            logger, logging.INFO,
            f"Database migrations applied: {applied}",
            entity_type="app",
            entity_id="migrations",
        )

    # Orchestrator oluştur ve başlat
    _orchestrator = Orchestrator()
    await _orchestrator.start()

    # ── Encrypted credential restore ──
    credential_ok = False
    balance_ok = False
    try:
        from backend.persistence.credential_persistence import load_encrypted
        creds = load_encrypted()
        if creds and creds.private_key:
            _orchestrator.credential_store.load(creds)
            credential_ok = True
            log_event(
                logger, logging.INFO,
                "Encrypted credential restored on startup",
                entity_type="app",
                entity_id="credential_restore",
            )
            # Balance fetch tetikle
            try:
                result = await _orchestrator.balance_manager.fetch()
                balance_ok = result is True
            except Exception:
                pass
    except Exception:
        pass  # Restore fail → modal açılır

    # ── StartupGuard: credential + balance zorunlu ──
    if credential_ok and balance_ok:
        _orchestrator.trading_enabled = True
        log_event(
            logger, logging.INFO,
            "StartupGuard: credential OK, balance OK — trading_enabled=True (immediate)",
            entity_type="app",
            entity_id="startup_guard",
        )
    elif credential_ok and not balance_ok:
        log_event(
            logger, logging.WARNING,
            "StartupGuard: credential OK, balance FAIL — degraded mode, retry active",
            entity_type="app",
            entity_id="startup_guard",
        )
        # Balance verify retry başlat — 30s aralıkla denemeye devam eder
        _orchestrator._start_verify_retry()
    else:
        log_event(
            logger, logging.INFO,
            "StartupGuard: no credential — waiting for user input",
            entity_type="app",
            entity_id="startup_guard",
        )

    # ── auto_start_bot_on_startup ──
    # Bot ancak credential + balance OK ise otomatik başlayabilir
    # Balance fail durumunda verify retry zaten çalışıyor (30s aralıkla)
    # Retry başarılı olunca trading_enabled=True → bot normal moda geçer
    auto_start = _orchestrator._config.trading.auto_start_bot_on_startup
    if auto_start and credential_ok and balance_ok:
        log_event(
            logger, logging.INFO,
            "Auto-start: bot running (credential OK, balance OK)",
            entity_type="app",
            entity_id="auto_start",
        )
    elif auto_start and credential_ok and not balance_ok:
        log_event(
            logger, logging.WARNING,
            "Auto-start: degraded — balance retry active, bot will start when ready",
            entity_type="app",
            entity_id="auto_start",
        )
        # verify_retry zaten başlatıldı (yukarıda)
        # Başarılı olunca trading_enabled=True → loop'lar zaten çalışıyor
    elif auto_start and not credential_ok:
        log_event(
            logger, logging.WARNING,
            "Auto-start: SKIPPED — no credential, waiting for user input",
            entity_type="app",
            entity_id="auto_start",
        )

    yield

    # Graceful shutdown
    if _orchestrator:
        await _orchestrator.stop()
        _orchestrator = None

    # Database close
    from backend.persistence.database import close_db
    await close_db()

    log_event(
        logger, logging.INFO,
        "Polyfast shut down",
        entity_type="app",
        entity_id="shutdown",
    )


app = FastAPI(
    title="Polyfast",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(bot_router, prefix="/api")
app.include_router(coin_router, prefix="/api")
app.include_router(credential_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
