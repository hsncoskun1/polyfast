"""Dashboard API endpoints — READ-ONLY data for frontend.

Backend davranisina DOKUNMAZ — sadece mevcut state'i okur ve sunar.
Tum veriler Orchestrator'daki in-memory state'ten gelir.

v0.8.0-backend-contract:
- DashboardOverview genisletildi (counters + session pnl + bot_status)
- PositionSummary genisletildi (variant, live, exits, activity)
- Placeholder-first: yeni alanlar optional, orchestrator hazir degilse None
- Frontend null-safe tuketir, eksik alan = mock fallback
"""

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.api.health import BotStatusContract, _build_bot_status

router = APIRouter()


# ── Response modelleri ──

# v0.8.0-backend-contract: shared contract fragments (frontend eventTypes.ts karsiliklari)

PnlTone = Literal["profit", "loss", "neutral", "pending", "off"]
ActivitySeverity = Literal["success", "warning", "error", "info", "pending", "off"]


class ActivityContract(BaseModel):
    """Frontend ActivityStatusLine icin bildirim/aktivite metni.

    text  → gorunen ana mesaj
    severity → tone (success/warning/error/info/pending/off)
    inline_icons → text icinde __KEY__ placeholder'lariyla render edilecek ikonlar
    """

    text: str
    severity: Optional[ActivitySeverity] = None
    inline_icons: Optional[list[str]] = None


class PositionLiveContract(BaseModel):
    """Open variant canli fiyat + delta ozeti (frontend PositionState)."""

    side: Literal["UP", "DOWN"]
    entry: str            # share price, "83"
    live: str             # share price, "85.6"
    delta_text: Optional[str] = None  # orn "+2.6" (opsiyonel, frontend de hesaplayabilir)


class PositionExitsContract(BaseModel):
    """Open variant cikis esikleri (frontend PositionExits).

    Tum alanlar config esigi, CANLI DURUM DEGIL. Frontend ExitGrid
    bu alanlari sadece esik olarak render eder — TP yaklasiyor gibi
    canli uyarilar ActivityContract'tan gelir.
    """

    tp: str             # "87"
    sl: str             # "81"
    fs: str             # "30s" countdown metni
    fs_pnl: Optional[str] = None  # "-5%" opsiyonel FS PnL esigi


class PositionSummary(BaseModel):
    """Pozisyon ozet kaydi.

    Legacy alanlar (geriye uyumluluk): position_id, asset, side, state,
    fill_price, requested_amount_usd, net_position_shares, close_reason,
    net_realized_pnl, created_at

    v0.8.0 extended alanlar (tumu optional):
    - variant: 'open' | 'claim'  (frontend EventTileVariant hint)
    - live: PositionLiveContract (canli fiyat ozeti)
    - exits: PositionExitsContract (cikis esikleri)
    - pnl_big: '+3.1%' formatli yuzde
    - pnl_amount: '+0.31$' formatli USD delta
    - pnl_tone: profit | loss | neutral | pending | off
    - activity: ActivityContract (canli bildirim metni)
    - event_url: Polymarket event sayfasi
    """

    # Legacy
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

    # v0.8.0 extended (optional, placeholder-first)
    variant: Optional[Literal["open", "claim"]] = None
    live: Optional[PositionLiveContract] = None
    exits: Optional[PositionExitsContract] = None
    pnl_big: Optional[str] = None
    pnl_amount: Optional[str] = None
    pnl_tone: Optional[PnlTone] = None
    activity: Optional[ActivityContract] = None
    event_url: Optional[str] = None


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
    """v0.8.0-backend-contract: frontend DashboardHeader icin extended kontrat.

    Mevcut legacy alanlar korundu (geriye uyumluluk). Yeni alanlar OPTIONAL:
    orchestrator henuz surmuyorsa None doner, frontend mock fallback'e duser.
    """

    # Legacy alanlar (korundu)
    trading_enabled: bool
    balance: BalanceInfo
    open_positions: int
    pending_claims: int
    session_trade_count: int
    configured_coins: int
    eligible_coins: int

    # v0.8.0-backend-contract: extended alanlar (optional, placeholder-first)
    bot_status: Optional[BotStatusContract] = None
    bakiye_text: Optional[str] = None
    kullanilabilir_text: Optional[str] = None
    session_pnl: Optional[float] = None
    session_pnl_pct: Optional[float] = None
    acilan: Optional[int] = None
    gorulen: Optional[int] = None
    ag_rate: Optional[str] = None
    win: Optional[int] = None
    lost: Optional[int] = None
    winrate: Optional[str] = None


# ── Endpoints ──

def _get_orchestrator():
    from backend.main import get_orchestrator
    orch = get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not running")
    return orch


def _fmt_usd(v: float) -> str:
    """Format USD value for display — '$248.53'."""
    return f"${v:,.2f}"


def _fmt_pct(v: float) -> str:
    """Format percentage — '4.8%'."""
    return f"{v:.1f}%"


def _build_overview_extended(orch) -> dict:
    """Build v0.8.0 extended overview fields (placeholder-safe).

    Her alan defensive get — orchestrator henuz her sayaci surmuyorsa None.
    Frontend null-safe tuketir, eksik alan icin mock fallback'e duser.
    """
    tracker = orch.position_tracker
    balance = orch.balance_manager

    # Session PnL — tracker'dan topla (henuz degerli kaynak varsa)
    session_pnl = getattr(tracker, "session_net_pnl", None)
    session_pnl_pct: Optional[float] = None
    if session_pnl is not None:
        starting = getattr(tracker, "session_start_balance", None)
        if starting is not None and starting > 0:
            session_pnl_pct = (session_pnl / starting) * 100

    # Counters
    acilan = getattr(tracker, "session_fill_count", None)
    gorulen = getattr(tracker, "session_event_seen_count", None)
    ag_rate_val: Optional[str] = None
    if acilan is not None and gorulen is not None and gorulen > 0:
        ag_rate_val = _fmt_pct((acilan / gorulen) * 100)

    # Win / Lost / Winrate
    win = getattr(tracker, "session_win_count", None)
    lost = getattr(tracker, "session_lost_count", None)
    winrate_val: Optional[str] = None
    if win is not None and lost is not None:
        total = win + lost
        if total > 0:
            winrate_val = _fmt_pct((win / total) * 100)

    return {
        "bakiye_text": _fmt_usd(balance.total_balance) if balance.total_balance is not None else None,
        "kullanilabilir_text": _fmt_usd(balance.available_balance) if balance.available_balance is not None else None,
        "session_pnl": round(session_pnl, 2) if session_pnl is not None else None,
        "session_pnl_pct": round(session_pnl_pct, 2) if session_pnl_pct is not None else None,
        "acilan": acilan,
        "gorulen": gorulen,
        "ag_rate": ag_rate_val,
        "win": win,
        "lost": lost,
        "winrate": winrate_val,
    }


@router.get("/dashboard/overview", response_model=DashboardOverview)
async def get_overview() -> DashboardOverview:
    """Dashboard ana ozet — tek bakista tum durum.

    v0.8.0-backend-contract: extended alanlar (counters, session_pnl,
    bot_status). Orchestrator henuz surmuyorsa ilgili alan None doner.
    """
    orch = _get_orchestrator()

    balance = orch.balance_manager
    tracker = orch.position_tracker
    claims = orch.claim_manager
    settings = orch.settings_store

    # Extended fields — placeholder-safe
    extended = _build_overview_extended(orch)

    # Bot status — health endpoint'in yardimcisini reuse ederek
    from backend.main import get_uptime

    bot_status = _build_bot_status(get_uptime())

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
        # v0.8.0-backend-contract extended
        bot_status=bot_status,
        **extended,
    )


def _derive_position_variant(p) -> Literal["open", "claim"]:
    """Position state + needs_redeem'den frontend variant hint'i uret.

    - needs_redeem=True (EXPIRY ile kapanmis, token elde) → 'claim'
    - is_open ve aktif → 'open'
    - default → 'open' (pending/close_pending/close_failed vb)
    """
    if getattr(p, "is_closed", False) and getattr(p, "needs_redeem", False):
        return "claim"
    return "open"


def _derive_pnl_tone(net_pnl: Optional[float]) -> Optional[PnlTone]:
    """Net PnL'den PnlTone turet.

    None → None (frontend default'a duser)
    >0   → 'profit'
    <0   → 'loss'
    ==0  → 'neutral'
    """
    if net_pnl is None:
        return None
    if net_pnl > 0:
        return "profit"
    if net_pnl < 0:
        return "loss"
    return "neutral"


def _format_pnl_pct(pct: Optional[float]) -> Optional[str]:
    """+3.1% / -2.4% formatli yuzde."""
    if pct is None:
        return None
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}%"


def _format_pnl_amount(amount: Optional[float]) -> Optional[str]:
    """+0.31$ / -0.18$ formatli dolar."""
    if amount is None:
        return None
    sign = "+" if amount >= 0 else ""
    return f"{sign}{amount:.2f}$"


def _build_position_contract(p, live_context: dict | None = None) -> PositionSummary:
    """PositionRecord'dan extended PositionSummary uretir.

    live_context: opsiyonel dict — {current_price, live_coin_price, exits, event_url, activity}
    Henuz wire edilmediyse None, frontend mock fallback'e duser.
    """
    # Legacy fields
    legacy = {
        "position_id": p.position_id,
        "asset": p.asset,
        "side": p.side,
        "state": p.state.value,
        "fill_price": p.fill_price,
        "requested_amount_usd": p.requested_amount_usd,
        "net_position_shares": p.net_position_shares,
        "close_reason": p.close_reason.value if p.close_reason else None,
        "net_realized_pnl": p.net_realized_pnl,
        "created_at": p.created_at.isoformat(),
    }

    # Variant hint
    variant = _derive_position_variant(p)

    # Live snapshot (context verilmis veya tracker'dan cek)
    live_obj: Optional[PositionLiveContract] = None
    pnl_big: Optional[str] = None
    pnl_amount: Optional[str] = None
    pnl_tone: Optional[PnlTone] = None

    if live_context and "current_price" in live_context:
        current_price = live_context["current_price"]
        # calculate_unrealized_pnl mevcut metot
        try:
            pnl_data = p.calculate_unrealized_pnl(current_price)
            net_pnl = pnl_data.get("net_unrealized_pnl_estimate")
            net_pnl_pct = pnl_data.get("net_unrealized_pnl_pct")
            pnl_big = _format_pnl_pct(net_pnl_pct)
            pnl_amount = _format_pnl_amount(net_pnl)
            pnl_tone = _derive_pnl_tone(net_pnl)
        except Exception:
            pass

        # Live share price stringi
        live_obj = PositionLiveContract(
            side="UP" if p.side.upper() == "UP" else "DOWN",
            entry=f"{p.fill_price:.2f}".rstrip("0").rstrip("."),
            live=f"{current_price:.2f}".rstrip("0").rstrip("."),
        )
    elif p.is_closed and p.net_realized_pnl is not None:
        # Kapali pozisyon icin gerceklesmis net pnl
        pnl_amount = _format_pnl_amount(p.net_realized_pnl)
        pnl_tone = _derive_pnl_tone(p.net_realized_pnl)
        if p.requested_amount_usd > 0:
            pct = (p.net_realized_pnl / p.requested_amount_usd) * 100
            pnl_big = _format_pnl_pct(pct)

    # Exits — live_context'ten veya None
    exits_obj: Optional[PositionExitsContract] = None
    if live_context and "exits" in live_context:
        e = live_context["exits"]
        exits_obj = PositionExitsContract(
            tp=str(e.get("tp", "")),
            sl=str(e.get("sl", "")),
            fs=str(e.get("fs", "")),
            fs_pnl=e.get("fs_pnl"),
        )

    # Activity
    activity_obj: Optional[ActivityContract] = None
    if live_context and "activity" in live_context:
        a = live_context["activity"]
        if isinstance(a, dict) and "text" in a:
            activity_obj = ActivityContract(
                text=a["text"],
                severity=a.get("severity"),
                inline_icons=a.get("inline_icons"),
            )

    event_url = live_context.get("event_url") if live_context else None

    return PositionSummary(
        **legacy,
        variant=variant,
        live=live_obj,
        exits=exits_obj,
        pnl_big=pnl_big,
        pnl_amount=pnl_amount,
        pnl_tone=pnl_tone,
        activity=activity_obj,
        event_url=event_url,
    )


@router.get("/dashboard/positions", response_model=list[PositionSummary])
async def get_positions() -> list[PositionSummary]:
    """Tum pozisyonlari listele (legacy + v0.8.0 extended alanlar).

    Placeholder-safe: live_context orchestrator'dan geldigi gibi kullanilir.
    Orchestrator henuz live price/exits/activity saglamiyorsa ilgili alanlar
    None doner, frontend mock fallback'e duser.
    """
    orch = _get_orchestrator()

    # Live context (henuz implementasyonda yok — placeholder None)
    # Orchestrator wire edildiginde her pozisyon icin asagidaki sekilde
    # live_context hazirlanacak:
    #   {
    #     "current_price": float,   # live share price
    #     "exits": {"tp": "87", "sl": "81", "fs": "30s", "fs_pnl": "-5%"},
    #     "activity": {"text": "● TP yaklasiyor", "severity": "success"},
    #     "event_url": "https://polymarket.com/event/...",
    #   }
    def _get_live_context(position) -> Optional[dict]:
        builder = getattr(orch, "build_position_live_context", None)
        if callable(builder):
            try:
                ctx = builder(position)
                return ctx if isinstance(ctx, dict) else None
            except Exception:
                return None
        return None

    return [
        _build_position_contract(p, live_context=_get_live_context(p))
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
