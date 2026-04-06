"""Dashboard API endpoints — READ-ONLY data for frontend.

Backend davranisina DOKUNMAZ — sadece mevcut state'i okur ve sunar.
Tum veriler Orchestrator'daki in-memory state'ten gelir.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


# ── Response modelleri ──

class PositionSummary(BaseModel):
    position_id: str
    asset: str
    side: str
    state: str
    fill_price: float
    requested_amount_usd: float
    net_position_shares: float
    close_reason: str | None = None
    net_realized_pnl: float = 0.0
    created_at: str


class ClaimSummary(BaseModel):
    claim_id: str
    asset: str
    position_id: str
    claim_status: str
    outcome: str
    claimed_amount_usdc: float
    retry_count: int


class BalanceInfo(BaseModel):
    available: float
    total: float
    is_stale: bool
    age_seconds: float


class TradingStatus(BaseModel):
    trading_enabled: bool
    open_positions: int
    pending_claims: int
    session_trade_count: int
    settlement_pending: int


class CoinSettingSummary(BaseModel):
    coin: str
    coin_enabled: bool
    side_mode: str
    order_amount: float
    is_configured: bool
    is_trade_eligible: bool


class DashboardOverview(BaseModel):
    trading_enabled: bool
    balance: BalanceInfo
    open_positions: int
    pending_claims: int
    session_trade_count: int
    configured_coins: int
    eligible_coins: int


# ── Endpoints ──

def _get_orchestrator():
    from backend.main import get_orchestrator
    orch = get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not running")
    return orch


@router.get("/dashboard/overview", response_model=DashboardOverview)
async def get_overview() -> DashboardOverview:
    """Dashboard ana ozet — tek bakista tum durum."""
    orch = _get_orchestrator()

    balance = orch.balance_manager
    tracker = orch.position_tracker
    claims = orch.claim_manager
    settings = orch.settings_store

    return DashboardOverview(
        trading_enabled=orch.trading_enabled,
        balance=BalanceInfo(
            available=balance.available_balance,
            total=balance.total_balance,
            is_stale=balance.is_stale,
            age_seconds=round(balance.age_seconds, 1),
        ),
        open_positions=tracker.open_position_count,
        pending_claims=claims.pending_count,
        session_trade_count=tracker.session_trade_count,
        configured_coins=len(settings.get_configured_coins()),
        eligible_coins=settings.eligible_count,
    )


@router.get("/dashboard/positions", response_model=list[PositionSummary])
async def get_positions() -> list[PositionSummary]:
    """Tum pozisyonlari listele."""
    orch = _get_orchestrator()

    return [
        PositionSummary(
            position_id=p.position_id,
            asset=p.asset,
            side=p.side,
            state=p.state.value,
            fill_price=p.fill_price,
            requested_amount_usd=p.requested_amount_usd,
            net_position_shares=p.net_position_shares,
            close_reason=p.close_reason.value if p.close_reason else None,
            net_realized_pnl=p.net_realized_pnl,
            created_at=p.created_at.isoformat(),
        )
        for p in orch.position_tracker.get_all_positions()
    ]


@router.get("/dashboard/claims", response_model=list[ClaimSummary])
async def get_claims() -> list[ClaimSummary]:
    """Tum claim/redeem kayitlarini listele."""
    orch = _get_orchestrator()

    claims = []
    for c in orch.claim_manager.get_pending_claims():
        claims.append(ClaimSummary(
            claim_id=c.claim_id,
            asset=c.asset,
            position_id=c.position_id,
            claim_status=c.claim_status.value,
            outcome=c.outcome.value,
            claimed_amount_usdc=c.claimed_amount_usdc,
            retry_count=c.retry_count,
        ))
    return claims


@router.get("/dashboard/settings", response_model=list[CoinSettingSummary])
async def get_settings() -> list[CoinSettingSummary]:
    """Tum coin ayarlarini listele."""
    orch = _get_orchestrator()

    return [
        CoinSettingSummary(
            coin=s.coin,
            coin_enabled=s.coin_enabled,
            side_mode=s.side_mode.value,
            order_amount=s.order_amount,
            is_configured=s.is_configured,
            is_trade_eligible=s.is_trade_eligible,
        )
        for s in orch.settings_store.get_all()
    ]


@router.get("/dashboard/trading-status", response_model=TradingStatus)
async def get_trading_status() -> TradingStatus:
    """Trading durumu — degraded mode kontrolu."""
    orch = _get_orchestrator()

    return TradingStatus(
        trading_enabled=orch.trading_enabled,
        open_positions=orch.position_tracker.open_position_count,
        pending_claims=orch.claim_manager.pending_count,
        session_trade_count=orch.position_tracker.session_trade_count,
        settlement_pending=orch.settlement.pending_retry_count,
    )
