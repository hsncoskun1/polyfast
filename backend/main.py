"""Polyfast Backend — FastAPI Application Entry Point."""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.health import router as health_router
from backend.version import __version__

_start_time: float = 0.0


def get_uptime() -> float:
    """Return seconds since application start."""
    return time.time() - _start_time


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    global _start_time
    _start_time = time.time()
    yield


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
