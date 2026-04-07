"""v0.8.0-backend-contract: Dashboard extended contract tests.

Frontend J2 hook'unun bekledigi alanlari test eder:
- /api/dashboard/overview: bot_status + counters + session pnl + winrate
- /api/dashboard/positions: variant + live + exits + pnl + activity

Orchestrator runtime olmadan endpoint cagrilacagi icin stub bir orchestrator
dependency inject edilir. Boylece contract shape'i wiring detayindan bagimsiz
test edilir.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from httpx import AsyncClient, ASGITransport

from backend.execution.claim_manager import ClaimOutcome, ClaimRecord, ClaimStatus
from backend.execution.close_reason import CloseReason
from backend.execution.position_record import PositionRecord, PositionState
from backend.main import app


def _make_position(
    position_id: str = "pos-btc-1",
    asset: str = "BTC",
    side: str = "UP",
    state: PositionState = PositionState.OPEN_CONFIRMED,
    fill_price: float = 0.83,
    requested_amount_usd: float = 2.00,
    net_position_shares: float = 2.40,
    close_reason: CloseReason | None = None,
    net_realized_pnl: float = 0.0,
    fee_rate: float = 0.02,
) -> PositionRecord:
    """Test helper — minimum dolu PositionRecord."""
    return PositionRecord(
        position_id=position_id,
        asset=asset,
        side=side,
        condition_id=f"cond-{position_id}",
        token_id=f"tok-{position_id}",
        state=state,
        fill_price=fill_price,
        requested_amount_usd=requested_amount_usd,
        gross_fill_shares=net_position_shares + 0.1,
        entry_fee_shares=0.1,
        net_position_shares=net_position_shares,
        fee_rate=fee_rate,
        close_reason=close_reason,
        net_realized_pnl=net_realized_pnl,
        created_at=datetime.now(timezone.utc),
    )


def _make_claim(
    claim_id: str = "claim-1",
    asset: str = "SOL",
    position_id: str = "pos-sol-1",
    claim_status: ClaimStatus = ClaimStatus.PENDING,
    outcome: ClaimOutcome = ClaimOutcome.PENDING,
    claimed_amount_usdc: float = 0.0,
    retry_count: int = 0,
) -> ClaimRecord:
    """Test helper — minimum dolu ClaimRecord."""
    return ClaimRecord(
        claim_id=claim_id,
        condition_id=f"cond-{claim_id}",
        position_id=position_id,
        asset=asset,
        side="UP",
        claim_status=claim_status,
        outcome=outcome,
        claimed_amount_usdc=claimed_amount_usdc,
        retry_count=retry_count,
    )


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
        max_retries=5,
        retry_schedule=[5, 10],
        retry_steady=20,
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


# ─── /api/dashboard/positions — extended contract tests ────────────


@pytest.mark.asyncio
async def test_positions_returns_503_without_orchestrator():
    """Orchestrator None iken positions 503 doner (mevcut davranis korundu)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/positions")

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_positions_empty_list_when_no_positions(stub_orchestrator):
    """Orchestrator var ama pozisyon yoksa bos liste doner."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/positions")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_positions_legacy_shape_preserved(stub_orchestrator):
    """Legacy alanlar korundu (position_id, asset, side, state, vb)."""
    pos = _make_position()
    stub_orchestrator.position_tracker.get_all_positions = lambda: [pos]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/positions")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    p = data[0]
    assert p["position_id"] == "pos-btc-1"
    assert p["asset"] == "BTC"
    assert p["side"] == "UP"
    assert p["state"] == "open_confirmed"
    assert p["fill_price"] == 0.83
    assert p["requested_amount_usd"] == 2.00
    assert p["net_realized_pnl"] == 0.0
    assert "created_at" in p


@pytest.mark.asyncio
async def test_positions_has_extended_fields(stub_orchestrator):
    """v0.8.0: tum extended field'lar response'da (None dahil)."""
    pos = _make_position()
    stub_orchestrator.position_tracker.get_all_positions = lambda: [pos]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/positions")

    p = resp.json()[0]
    extended = {"variant", "live", "exits", "pnl_big", "pnl_amount", "pnl_tone", "activity", "event_url"}
    assert extended.issubset(p.keys())


@pytest.mark.asyncio
async def test_positions_open_variant_without_live_context(stub_orchestrator):
    """Open pozisyon, live_context yok → variant='open', live/exits/activity None."""
    pos = _make_position(state=PositionState.OPEN_CONFIRMED)
    stub_orchestrator.position_tracker.get_all_positions = lambda: [pos]
    # build_position_live_context attribute yok → None context

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/positions")

    p = resp.json()[0]
    assert p["variant"] == "open"
    assert p["live"] is None
    assert p["exits"] is None
    assert p["activity"] is None


@pytest.mark.asyncio
async def test_positions_claim_variant_for_redeemable_closed(stub_orchestrator):
    """Kapali ve needs_redeem (EXPIRY) ise variant='claim'."""
    pos = _make_position(
        state=PositionState.CLOSED,
        close_reason=CloseReason.EXPIRY,
        net_realized_pnl=0.5,
    )
    stub_orchestrator.position_tracker.get_all_positions = lambda: [pos]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/positions")

    p = resp.json()[0]
    assert p["variant"] == "claim"
    # Realized pnl'den pnl_tone hesaplanmali
    assert p["pnl_tone"] == "profit"
    assert p["pnl_amount"] is not None
    assert "+" in p["pnl_amount"]


@pytest.mark.asyncio
async def test_positions_open_variant_with_live_context(stub_orchestrator):
    """build_position_live_context provider varsa live/exits/activity doluyor."""
    pos = _make_position(
        fill_price=0.80,
        net_position_shares=2.50,
        requested_amount_usd=2.00,
    )
    stub_orchestrator.position_tracker.get_all_positions = lambda: [pos]

    def _builder(_p):
        return {
            "current_price": 0.84,
            "exits": {"tp": "87", "sl": "78", "fs": "30s", "fs_pnl": "-5%"},
            "activity": {"text": "● TP yaklasiyor — hedef 87", "severity": "success"},
            "event_url": "https://polymarket.com/event/bitcoin-up-or-down-5-min",
        }

    stub_orchestrator.build_position_live_context = _builder

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/positions")

    p = resp.json()[0]
    assert p["variant"] == "open"
    # Live snapshot
    assert p["live"] is not None
    assert p["live"]["side"] == "UP"
    # Exits
    assert p["exits"] is not None
    assert p["exits"]["tp"] == "87"
    assert p["exits"]["sl"] == "78"
    assert p["exits"]["fs"] == "30s"
    assert p["exits"]["fs_pnl"] == "-5%"
    # Activity
    assert p["activity"] is not None
    assert p["activity"]["text"] == "● TP yaklasiyor — hedef 87"
    assert p["activity"]["severity"] == "success"
    # Event url
    assert p["event_url"] == "https://polymarket.com/event/bitcoin-up-or-down-5-min"
    # Pnl derived from live (0.84 > 0.80 → profit)
    assert p["pnl_tone"] == "profit"
    assert p["pnl_big"] is not None
    assert "+" in p["pnl_big"]


@pytest.mark.asyncio
async def test_positions_loss_tone_for_negative_pnl(stub_orchestrator):
    """DOWN pozisyon, canli fiyat yukari → net pnl negatif → loss tonu."""
    pos = _make_position(
        side="DOWN",
        fill_price=0.55,
        net_position_shares=3.50,
        requested_amount_usd=2.00,
    )
    stub_orchestrator.position_tracker.get_all_positions = lambda: [pos]

    def _builder(_p):
        # DOWN pozisyonu, canli fiyat 0.50 → DOWN icin net negatif
        return {"current_price": 0.40}

    stub_orchestrator.build_position_live_context = _builder

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/positions")

    p = resp.json()[0]
    assert p["live"] is not None
    # Net pnl negatif olmali (shares * current_price < requested)
    assert p["pnl_tone"] == "loss"
    assert p["pnl_amount"] is not None
    assert "-" in p["pnl_amount"]


@pytest.mark.asyncio
async def test_positions_multiple_mix(stub_orchestrator):
    """Birden fazla pozisyon — open + claim variant karisik."""
    open_pos = _make_position(position_id="p1", asset="BTC")
    claim_pos = _make_position(
        position_id="p2",
        asset="ETH",
        state=PositionState.CLOSED,
        close_reason=CloseReason.EXPIRY,
    )
    stub_orchestrator.position_tracker.get_all_positions = lambda: [open_pos, claim_pos]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/positions")

    data = resp.json()
    assert len(data) == 2
    variants = {p["asset"]: p["variant"] for p in data}
    assert variants["BTC"] == "open"
    assert variants["ETH"] == "claim"


# ─── /api/dashboard/claims — extended contract tests ────────────────


@pytest.mark.asyncio
async def test_claims_returns_503_without_orchestrator():
    """Orchestrator None iken claims 503 doner (mevcut davranis korundu)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/claims")

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_claims_empty_list_when_no_claims(stub_orchestrator):
    """Orchestrator var ama claim yoksa bos liste doner."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/claims")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_claims_legacy_shape_preserved(stub_orchestrator):
    """Legacy alanlar korundu (claim_id, asset, position_id, retry_count)."""
    c = _make_claim(claim_id="claim-1", asset="SOL", retry_count=3)
    stub_orchestrator.claim_manager.get_pending_claims = lambda: [c]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/claims")

    data = resp.json()[0]
    assert data["claim_id"] == "claim-1"
    assert data["asset"] == "SOL"
    assert data["position_id"] == "pos-sol-1"
    assert data["retry_count"] == 3
    assert data["claim_status"] == "pending"


@pytest.mark.asyncio
async def test_claims_has_extended_fields(stub_orchestrator):
    """v0.8.0: status, retry, max_retry, next_sec, payout response'ta."""
    c = _make_claim()
    stub_orchestrator.claim_manager.get_pending_claims = lambda: [c]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/claims")

    data = resp.json()[0]
    extended = {"status", "retry", "max_retry", "next_sec", "payout"}
    assert extended.issubset(data.keys())


@pytest.mark.asyncio
async def test_claims_status_enum_align_pending_to_retry(stub_orchestrator):
    """PENDING (backend) → RETRY (frontend contract)."""
    c = _make_claim(claim_status=ClaimStatus.PENDING)
    stub_orchestrator.claim_manager.get_pending_claims = lambda: [c]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/claims")

    assert resp.json()[0]["status"] == "RETRY"


@pytest.mark.asyncio
async def test_claims_status_enum_align_success_to_ok(stub_orchestrator):
    """SUCCESS (backend) → OK (frontend contract).

    Bu test _map_claim_status_to_contract mapping'ini dogrudan test eder.
    """
    from backend.api.dashboard import _map_claim_status_to_contract

    assert _map_claim_status_to_contract("pending") == "RETRY"
    assert _map_claim_status_to_contract("success") == "OK"
    assert _map_claim_status_to_contract("failed") == "FAIL"
    # unknown -> RETRY (safe default)
    assert _map_claim_status_to_contract("weird") == "RETRY"


@pytest.mark.asyncio
async def test_claims_retry_fields_populated(stub_orchestrator):
    """retry + max_retry + next_sec degerleri populated."""
    c = _make_claim(retry_count=1)
    stub_orchestrator.claim_manager.get_pending_claims = lambda: [c]
    # max_retries=5, retry_schedule=[5,10], retry_steady=20

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/claims")

    data = resp.json()[0]
    assert data["retry"] == 1
    assert data["max_retry"] == 5
    # retry_count=1 → schedule[1] = 10s
    assert data["next_sec"] == 10


@pytest.mark.asyncio
async def test_claims_next_sec_steady_after_schedule(stub_orchestrator):
    """retry_count >= schedule length → retry_steady (20s)."""
    c = _make_claim(retry_count=5)  # schedule 2 elemanli, 5 > 2
    stub_orchestrator.claim_manager.get_pending_claims = lambda: [c]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/claims")

    data = resp.json()[0]
    assert data["next_sec"] == 20  # steady delay


@pytest.mark.asyncio
async def test_claims_payout_none_when_not_claimed(stub_orchestrator):
    """claimed_amount_usdc=0 iken payout None."""
    c = _make_claim(claimed_amount_usdc=0.0)
    stub_orchestrator.claim_manager.get_pending_claims = lambda: [c]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/claims")

    assert resp.json()[0]["payout"] is None


@pytest.mark.asyncio
async def test_claims_payout_formatted_when_claimed(stub_orchestrator):
    """claimed_amount_usdc>0 iken payout '$5.83' formatli."""
    c = _make_claim(
        claim_status=ClaimStatus.SUCCESS,
        outcome=ClaimOutcome.REDEEMED_WON,
        claimed_amount_usdc=5.83,
    )
    # SUCCESS claim get_pending_claims'te olmaz, direkt list dondur
    stub_orchestrator.claim_manager.get_pending_claims = lambda: [c]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/claims")

    data = resp.json()[0]
    assert data["payout"] == "$5.83"
    assert data["status"] == "OK"


# ─── /api/dashboard/search — extended contract tests ───────────────


def _make_search_entry(
    tile_id: str = "search-btc-1",
    coin: str = "BTC",
    all_pass: bool = True,
    **overrides,
) -> dict:
    """Test helper — orchestrator'dan gelecek ham search entry dict."""
    state = "pass" if all_pass else "waiting"
    rules = [
        {"label": "Zaman", "live_value": "3:07", "threshold_text": "30-270s", "state": state},
        {"label": "Fiyat", "live_value": "83", "threshold_text": "≥80", "state": state},
        {"label": "Delta", "live_value": "$55", "threshold_text": "≥$50", "state": state},
        {"label": "Spread", "live_value": "1.8%", "threshold_text": "≤3%", "state": state},
        {"label": "EvMax", "live_value": "0/1", "threshold_text": "1", "state": state},
        {"label": "BotMax", "live_value": "1/2", "threshold_text": "2", "state": state},
    ]
    entry = {
        "tile_id": tile_id,
        "coin": coin,
        "event_url": f"https://polymarket.com/event/{coin.lower()}-5m",
        "pnl_big": "6/6" if all_pass else "4/6",
        "pnl_amount": "HAZIR" if all_pass else "BEKLE",
        "pnl_tone": "profit" if all_pass else "pending",
        "ptb": "82.50",
        "live": "83.00",
        "delta": "0.50",
        "rules": rules,
        "type": "ok" if all_pass else "wait",
    }
    entry.update(overrides)
    return entry


@pytest.mark.asyncio
async def test_search_returns_503_without_orchestrator():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/search")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_search_empty_when_provider_missing(stub_orchestrator):
    """build_search_snapshot yoksa bos liste doner (placeholder-safe)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/search")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_search_empty_when_provider_returns_empty(stub_orchestrator):
    stub_orchestrator.build_search_snapshot = lambda: []
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/search")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_search_contract_shape_full(stub_orchestrator):
    """Full search tile contract alanlari response'da."""
    entry = _make_search_entry()
    stub_orchestrator.build_search_snapshot = lambda: [entry]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/search")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    t = data[0]
    expected = {
        "tile_id", "coin", "event_url", "pnl_big", "pnl_amount",
        "pnl_tone", "ptb", "live", "delta", "rules", "activity",
        "signal_ready", "type",
    }
    assert expected.issubset(t.keys())
    assert t["coin"] == "BTC"
    assert t["tile_id"] == "search-btc-1"
    assert len(t["rules"]) == 6


@pytest.mark.asyncio
async def test_search_signal_ready_true_when_all_pass(stub_orchestrator):
    """Tum rules 'pass' ise signal_ready true (raw signal_ready verilmedi)."""
    entry = _make_search_entry(all_pass=True)
    entry.pop("signal_ready", None)
    stub_orchestrator.build_search_snapshot = lambda: [entry]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/search")

    assert resp.json()[0]["signal_ready"] is True


@pytest.mark.asyncio
async def test_search_signal_ready_false_when_any_waiting(stub_orchestrator):
    """Rules icinde waiting varsa signal_ready false."""
    entry = _make_search_entry(all_pass=False)
    stub_orchestrator.build_search_snapshot = lambda: [entry]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/search")

    assert resp.json()[0]["signal_ready"] is False


@pytest.mark.asyncio
async def test_search_raw_signal_ready_wins_over_derived(stub_orchestrator):
    """Ham signal_ready verilmisse rules'tan turetilene oncelikli."""
    entry = _make_search_entry(all_pass=True, signal_ready=False)
    stub_orchestrator.build_search_snapshot = lambda: [entry]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/search")

    assert resp.json()[0]["signal_ready"] is False


@pytest.mark.asyncio
async def test_search_rules_state_enum_mapping(stub_orchestrator):
    """Rule state Literal enum degerleri dogru mapping'leniyor."""
    entry = _make_search_entry()
    entry["rules"][0]["state"] = "disabled"
    entry["rules"][1]["state"] = "fail"
    entry["rules"][2]["state"] = "waiting"
    stub_orchestrator.build_search_snapshot = lambda: [entry]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/search")

    rules = resp.json()[0]["rules"]
    assert rules[0]["state"] == "disabled"
    assert rules[1]["state"] == "fail"
    assert rules[2]["state"] == "waiting"
    assert rules[3]["state"] == "pass"


@pytest.mark.asyncio
async def test_search_activity_optional(stub_orchestrator):
    """activity field opsiyonel — verilirse serialize, yoksa None."""
    entry = _make_search_entry()
    entry["activity"] = {"text": "● Sinyal hazir", "severity": "success"}
    stub_orchestrator.build_search_snapshot = lambda: [entry]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/search")

    t = resp.json()[0]
    assert t["activity"] is not None
    assert t["activity"]["text"] == "● Sinyal hazir"
    assert t["activity"]["severity"] == "success"


@pytest.mark.asyncio
async def test_search_provider_exception_returns_empty(stub_orchestrator):
    """Provider exception firlatirsa bos liste + warning (sessiz bypass DEGIL, log var)."""
    def _boom():
        raise RuntimeError("provider crashed")
    stub_orchestrator.build_search_snapshot = _boom

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/search")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_search_multiple_mixed(stub_orchestrator):
    """Birden fazla tile — karisik all_pass/false."""
    stub_orchestrator.build_search_snapshot = lambda: [
        _make_search_entry(tile_id="s1", coin="BTC", all_pass=True),
        _make_search_entry(tile_id="s2", coin="ETH", all_pass=False),
        _make_search_entry(tile_id="s3", coin="SOL", all_pass=True),
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/search")

    data = resp.json()
    assert len(data) == 3
    by_coin = {t["coin"]: t for t in data}
    assert by_coin["BTC"]["signal_ready"] is True
    assert by_coin["ETH"]["signal_ready"] is False
    assert by_coin["SOL"]["signal_ready"] is True
