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

    # Orchestrator oluştur ve başlat
    _orchestrator = Orchestrator()
    await _orchestrator.start()

    # Encrypted credential restore — startup'ta otomatik yükleme
    try:
        from backend.persistence.credential_persistence import load_encrypted
        creds = load_encrypted()
        if creds and creds.private_key:
            _orchestrator.credential_store.load(creds)
            # Balance fetch tetikle (credential wiring)
            try:
                await _orchestrator.balance_manager.fetch()
            except Exception:
                pass  # Balance fetch fail → dashboard $0 gösterir, bloklamaz
            log_event(
                logger, logging.INFO,
                "Encrypted credential restored on startup",
                entity_type="app",
                entity_id="credential_restore",
            )
    except Exception:
        pass  # Restore fail → modal açılır, bloklamaz

    yield

    # Graceful shutdown
    if _orchestrator:
        await _orchestrator.stop()
        _orchestrator = None

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
