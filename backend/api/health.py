"""Health check endpoint — system liveness and component status."""

from fastapi import APIRouter
from pydantic import BaseModel

from backend.version import __version__

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    components: dict[str, str]


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return current system health status."""
    from backend.main import get_uptime

    return HealthResponse(
        status="ok",
        version=__version__,
        uptime_seconds=round(get_uptime(), 2),
        components={},
    )
