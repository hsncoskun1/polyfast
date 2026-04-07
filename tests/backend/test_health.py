"""Tests for health endpoint."""

import pytest
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.version import __version__


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_health_returns_ok():
    """Health endpoint returns 200 with correct structure."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == __version__
    assert "uptime_seconds" in data
    assert isinstance(data["uptime_seconds"], float)
    assert "components" in data
    assert isinstance(data["components"], dict)


@pytest.mark.asyncio
async def test_health_uptime_is_non_negative():
    """Uptime should be zero or positive."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")

    assert resp.json()["uptime_seconds"] >= 0


# ─── v0.8.0-backend-contract: BotStatusContract tests ──────────────


@pytest.mark.asyncio
async def test_health_contains_bot_status_field():
    """v0.8.0: /api/health response'inda bot_status field'i olmali."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")

    assert resp.status_code == 200
    data = resp.json()
    assert "bot_status" in data
    # Orchestrator yoksa bile bot_status none degil, objet doner
    assert data["bot_status"] is not None


@pytest.mark.asyncio
async def test_health_bot_status_has_expected_fields():
    """BotStatusContract tum beklenen alanlari icermeli (optional olabilirler)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")

    bot_status = resp.json()["bot_status"]
    expected_fields = {
        "running",
        "health",
        "restore_phase",
        "shutdown_in_progress",
        "startup_guard_blocked",
        "paused",
        "uptime_sec",
        "latency_ms",
    }
    # Pydantic optional alanlari da serialize eder (None dahil)
    assert expected_fields.issubset(bot_status.keys())


@pytest.mark.asyncio
async def test_health_bot_status_health_enum_valid():
    """BotStatusContract.health literal enum degerlerden biri olmali."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")

    bot_status = resp.json()["bot_status"]
    health = bot_status["health"]
    # Orchestrator yoksa 'unknown', varsa 'healthy' veya 'degraded'
    assert health in ("healthy", "degraded", "critical", "unknown")


@pytest.mark.asyncio
async def test_health_bot_status_uptime_sec_non_negative():
    """BotStatusContract.uptime_sec negatif olmamali."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")

    bot_status = resp.json()["bot_status"]
    uptime_sec = bot_status["uptime_sec"]
    # Orchestrator yoksa bile uptime_sec hesaplanir (get_uptime())
    assert uptime_sec is None or uptime_sec >= 0


@pytest.mark.asyncio
async def test_health_placeholder_safe_without_orchestrator():
    """Orchestrator None iken health endpoint dusmeyip bot_status unknown dondurmeli."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")

    # 200 olmali, orchestrator yoksa bile
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    # bot_status.health unknown (orchestrator None fallback'i)
    assert data["bot_status"]["health"] == "unknown"
