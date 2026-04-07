"""v0.8.0-backend-contract: DashboardOverview extended contract tests.

Frontend J2 hook'unun bekledigi alanlari test eder:
- bot_status (BotStatusContract)
- bakiye_text, kullanilabilir_text
- session_pnl, session_pnl_pct
- acilan, gorulen, ag_rate
- win, lost, winrate

Orchestrator runtime olmadan endpoint cagrilacagi icin stub bir orchestrator
dependency inject edilir. Boylece contract shape'i wiring detayindan bagimsiz
test edilir.
"""

from types import SimpleNamespace

import pytest
from httpx import AsyncClient, ASGITransport

from backend.main import app
import backend.api.dashboard as dashboard_module


@pytest.fixture
def stub_orchestrator(monkeypatch):
    """Fake orchestrator — sadece contract shape testi icin minimum state."""
    balance = SimpleNamespace(
        available_balance=236.13,
        total_balance=248.53,
        is_stale=False,
        age_seconds=1.2,
    )
    tracker = SimpleNamespace(
        open_position_count=3,
        session_trade_count=12,
        session_net_pnl=12.40,
        session_start_balance=236.13,
        session_fill_count=12,
        session_event_seen_count=248,
        session_win_count=8,
        session_lost_count=4,
        get_all_positions=lambda: [],
    )
    claims = SimpleNamespace(
        pending_count=1,
        get_pending_claims=lambda: [],
    )
    settings = SimpleNamespace(
        get_configured_coins=lambda: ["BTC", "ETH", "SOL"],
        eligible_count=3,
        get_all=lambda: [],
    )
    fake_orch = SimpleNamespace(
        trading_enabled=True,
        balance_manager=balance,
        position_tracker=tracker,
        claim_manager=claims,
        settings_store=settings,
        settlement=SimpleNamespace(pending_retry_count=0),
        restore_phase=False,
        shutdown_flag=False,
        paused=False,
        degraded_mode=False,
        startup_guard=SimpleNamespace(blocked=False),
    )

    def _fake_get_orchestrator():
        return fake_orch

    # Patch hem dashboard module'un import noktasini hem main'in get_orchestrator
    monkeypatch.setattr("backend.main.get_orchestrator", _fake_get_orchestrator)
    # dashboard.py icinde local import yaptigi icin runtime'da resolve olur
    return fake_orch


# ─── Placeholder-safe: orchestrator None iken ────────────────────────


@pytest.mark.asyncio
async def test_overview_returns_503_without_orchestrator():
    """Orchestrator None iken overview 503 doner (mevcut davranis korundu)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/overview")

    assert resp.status_code == 503


# ─── Extended contract: orchestrator stub ile ───────────────────────


@pytest.mark.asyncio
async def test_overview_contains_legacy_fields(stub_orchestrator):
    """Legacy alanlar korundu."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/overview")

    assert resp.status_code == 200
    data = resp.json()
    assert data["trading_enabled"] is True
    assert "balance" in data
    assert data["balance"]["total"] == 248.53
    assert data["balance"]["available"] == 236.13
    assert data["open_positions"] == 3
    assert data["pending_claims"] == 1
    assert data["session_trade_count"] == 12
    assert data["configured_coins"] == 3
    assert data["eligible_coins"] == 3


@pytest.mark.asyncio
async def test_overview_extended_has_bot_status(stub_orchestrator):
    """v0.8.0: bot_status field'i overview response'inda olmali."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/overview")

    data = resp.json()
    assert "bot_status" in data
    bot_status = data["bot_status"]
    assert bot_status is not None
    assert bot_status["running"] is True
    assert bot_status["health"] == "healthy"
    assert bot_status["paused"] is False


@pytest.mark.asyncio
async def test_overview_extended_has_text_balances(stub_orchestrator):
    """v0.8.0: bakiye_text ve kullanilabilir_text formatted USD."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/overview")

    data = resp.json()
    assert data["bakiye_text"] == "$248.53"
    assert data["kullanilabilir_text"] == "$236.13"


@pytest.mark.asyncio
async def test_overview_extended_has_session_pnl(stub_orchestrator):
    """v0.8.0: session_pnl + session_pnl_pct hesaplanmali."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/overview")

    data = resp.json()
    assert data["session_pnl"] == 12.40
    assert data["session_pnl_pct"] is not None
    assert data["session_pnl_pct"] > 0  # 12.40 / 236.13 * 100 ≈ 5.25%


@pytest.mark.asyncio
async def test_overview_extended_has_counters(stub_orchestrator):
    """v0.8.0: acilan / gorulen / ag_rate counter alanlari."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/overview")

    data = resp.json()
    assert data["acilan"] == 12
    assert data["gorulen"] == 248
    assert data["ag_rate"] is not None
    # 12 / 248 * 100 = 4.8%
    assert "4.8" in data["ag_rate"] or "4.9" in data["ag_rate"]


@pytest.mark.asyncio
async def test_overview_extended_has_winrate(stub_orchestrator):
    """v0.8.0: win / lost / winrate alanlari."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/overview")

    data = resp.json()
    assert data["win"] == 8
    assert data["lost"] == 4
    # 8 / (8+4) = 66.7%
    assert data["winrate"] is not None
    assert "66" in data["winrate"]


@pytest.mark.asyncio
async def test_overview_extended_all_expected_fields(stub_orchestrator):
    """v0.8.0: tum extended field'lar response'da olmali (None dahil)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/overview")

    data = resp.json()
    extended_fields = {
        "bot_status",
        "bakiye_text",
        "kullanilabilir_text",
        "session_pnl",
        "session_pnl_pct",
        "acilan",
        "gorulen",
        "ag_rate",
        "win",
        "lost",
        "winrate",
    }
    assert extended_fields.issubset(data.keys())
