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
