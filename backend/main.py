"""Polyfast Backend — FastAPI Application Entry Point.

Lifespan manages all orchestrator loops:
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
from backend.version import __version__
from backend.logging_config.service import get_logger, log_event

import logging

logger = get_logger("main")

_start_time: float = 0.0


def get_uptime() -> float:
    """Return seconds since application start."""
    return time.time() - _start_time


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown.

    Starts all orchestrator loops on startup.
    Gracefully stops them on shutdown.
    """
    global _start_time
    _start_time = time.time()

    log_event(
        logger, logging.INFO,
        f"Polyfast v{__version__} starting",
        entity_type="app",
        entity_id="startup",
    )

    # Orchestrator loops burada başlatılacak.
    # Şu an component'lar ayrı modüllerde tanımlı.
    # Tam wiring orchestrator/main_orchestrator.py'de yapılacak
    # ve buradan tek çağrıyla başlatılacak.
    #
    # Mevcut durum:
    # - DiscoveryLoop: backend/orchestrator/discovery_loop.py (start/stop ready)
    # - CoinPriceClient: backend/market_data/coin_price_client.py (start/stop ready)
    # - EvaluationLoop: backend/orchestrator/evaluation_loop.py (start/stop ready)
    #
    # Tam wiring için gerekli bağımlılıklar:
    # - DiscoveryEngine (PublicMarketClient gerektirir)
    # - SafeSync (Registry gerektirir)
    # - SettingsStore (coin settings)
    # - RTDSClient (CLOB WS)
    # - WSPriceBridge
    # - PTBFetcher (SSRPTBAdapter)
    # - LivePricePipeline
    # - RuleEngine
    #
    # Bu bağımlılıkların oluşturulması ve birbirine bağlanması
    # production'da yapılacak. Şu an test/doğrulama aşamasında.

    yield

    log_event(
        logger, logging.INFO,
        "Polyfast shutting down",
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
