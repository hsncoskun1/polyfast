"""Settlement + RelayerWrapper tests -- v0.6.5 + v0.6.6 retry lifecycle."""

import time
import pytest
from unittest.mock import AsyncMock, patch

from backend.orchestrator.settlement import (
    SettlementOrchestrator, SettlementRetryState,
)
from backend.execution.position_tracker import PositionTracker
from backend.execution.claim_manager import (
    ClaimManager, ClaimOutcome, ClaimStatus,
    CLAIM_REDEEM_MAX_RETRIES,
)
from backend.execution.balance_manager import BalanceManager
from backend.execution.close_reason import CloseReason
from backend.execution.relayer_client_wrapper import (
    RelayerClientWrapper, LIVE_SETTLEMENT_ENABLED,
)


def _make_closed_position(tracker, balance, fill=0.85, exit_price=0.92,
                           reason=CloseReason.TAKE_PROFIT, asset="BTC"):
    pos = tracker.create_pending(asset, "UP", "0x1", "tok1", 5.0)
    tracker.confirm_fill(pos.position_id, fill_price=fill)
    tracker.request_close(pos.position_id, reason)
    tracker.confirm_close(pos.position_id, exit_fill_price=exit_price)
    return pos


def _setup(paper=True):
    tracker = PositionTracker()
    balance = BalanceManager()
    balance.update(available=50.0)
    claim_mgr = ClaimManager(balance, paper_mode=paper)
    relayer = RelayerClientWrapper()
    orch = SettlementOrchestrator(tracker, claim_mgr, relayer, paper_mode=paper)
    return tracker, balance, claim_mgr, relayer, orch


# ===================================================================
# RELAYER WRAPPER
# ===================================================================

class TestRelayerWrapper:

    def test_live_settlement_guard(self):
        """LIVE_SETTLEMENT_ENABLED=False -> gercek TX cikmaz."""
        assert LIVE_SETTLEMENT_ENABLED is False

    @pytest.mark.asyncio
    async def test_redeem_blocked_by_guard(self):
        relayer = RelayerClientWrapper()
        result = await relayer.redeem_positions("0x1", "UP")
        assert result["success"] is False
        assert result["guard"] is True

    @pytest.mark.asyncio
    async def test_check_redeemable_placeholder(self):
        relayer = RelayerClientWrapper()
        result = await relayer.check_redeemable("0x1")
        assert result is True

    def test_not_initialized_without_creds(self):
        relayer = RelayerClientWrapper()
        assert relayer.is_initialized is False

    def test_initialized_with_creds(self):
        relayer = RelayerClientWrapper(
            private_key="0xabc", relayer_api_key="key", relayer_address="0x123",
        )
        assert relayer.is_initialized is True

    def test_separate_from_clob_wrapper(self):
        """RelayerWrapper clob_client_wrapper'dan AYRI dosya."""
        import backend.execution.relayer_client_wrapper as mod
        import backend.execution.clob_client_wrapper as clob_mod
        assert mod.__file__ != clob_mod.__file__


# ===================================================================
# SETTLEMENT ORCHESTRATION — TEMEL (v0.6.5)
# ===================================================================

class TestSettlementOrchestrator:

    @pytest.mark.asyncio
    async def test_settle_winning_position(self):
        """Kazanan pozisyon: redeem -> USDC, outcome=REDEEMED_WON."""
        tracker, balance, claim_mgr, _, orch = _setup()
        pos = _make_closed_position(tracker, balance, fill=0.85, exit_price=0.92)
        assert pos.net_realized_pnl > 0

        settled = await orch.process_settlements()
        assert settled == 1
        claims = claim_mgr.get_claims_by_position(pos.position_id)
        assert len(claims) == 1
        assert claims[0].outcome == ClaimOutcome.REDEEMED_WON
        assert claims[0].claimed_amount_usdc > 0

    @pytest.mark.asyncio
    async def test_settle_losing_position(self):
        """Kaybeden pozisyon: redeem -> $0, outcome=REDEEMED_LOST."""
        tracker, balance, claim_mgr, _, orch = _setup()
        pos = _make_closed_position(tracker, balance, fill=0.85, exit_price=0.78,
                                     reason=CloseReason.STOP_LOSS)
        assert pos.net_realized_pnl < 0

        settled = await orch.process_settlements()
        assert settled == 1
        claims = claim_mgr.get_claims_by_position(pos.position_id)
        assert claims[0].outcome == ClaimOutcome.REDEEMED_LOST
        assert claims[0].claimed_amount_usdc == 0.0

    @pytest.mark.asyncio
    async def test_already_settled_skipped(self):
        """Zaten settled pozisyon tekrar settle edilmez."""
        tracker, balance, claim_mgr, _, orch = _setup()
        _make_closed_position(tracker, balance)

        settled1 = await orch.process_settlements()
        assert settled1 == 1
        settled2 = await orch.process_settlements()
        assert settled2 == 0

    @pytest.mark.asyncio
    async def test_open_position_not_settled(self):
        """Acik pozisyon settle edilmez."""
        tracker, balance, claim_mgr, _, orch = _setup()
        pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 5.0)
        tracker.confirm_fill(pos.position_id, fill_price=0.85)

        settled = await orch.process_settlements()
        assert settled == 0

    @pytest.mark.asyncio
    async def test_balance_increases_on_win(self):
        tracker, balance, claim_mgr, _, orch = _setup()
        before = balance.available_balance
        _make_closed_position(tracker, balance, fill=0.85, exit_price=0.92)
        await orch.process_settlements()
        assert balance.available_balance > before

    @pytest.mark.asyncio
    async def test_balance_unchanged_on_loss(self):
        tracker, balance, claim_mgr, _, orch = _setup()
        _make_closed_position(tracker, balance, fill=0.85, exit_price=0.78,
                               reason=CloseReason.STOP_LOSS)
        before = balance.available_balance
        await orch.process_settlements()
        assert balance.available_balance == before


# ===================================================================
# SETTLEMENT RETRY LIFECYCLE (v0.6.6)
# ===================================================================

class TestSettlementRetryState:

    def test_first_retry_delay_zero(self):
        """Ilk deneme icin delay 0."""
        state = SettlementRetryState(position_id="p1", claim_id="c1")
        assert state.get_retry_delay() == 0.0

    def test_retry_schedule(self):
        """Retry schedule: 0 -> 5 -> 10 -> 20 -> 20..."""
        state = SettlementRetryState(position_id="p1", claim_id="c1")
        delays = []
        for _ in range(6):
            delays.append(state.get_retry_delay())
            state.attempt_count += 1
        # attempt_count: 0->0s, 1->5s, 2->10s, 3->20s, 4->20s, 5->20s
        assert delays == [0.0, 5.0, 10.0, 20.0, 20.0, 20.0]

    def test_exhausted_at_max(self):
        """Max retry asilinca exhausted=True."""
        state = SettlementRetryState(position_id="p1", claim_id="c1")
        for _ in range(CLAIM_REDEEM_MAX_RETRIES):
            state.schedule_next()
        assert state.exhausted is True

    def test_is_ready_when_time_passed(self):
        """next_retry_at gectiyse ready."""
        state = SettlementRetryState(
            position_id="p1", claim_id="c1",
            next_retry_at=time.time() - 1,  # gecmiste
        )
        assert state.is_ready() is True

    def test_not_ready_when_future(self):
        """next_retry_at gelecekteyse ready degil."""
        state = SettlementRetryState(
            position_id="p1", claim_id="c1",
            next_retry_at=time.time() + 100,  # gelecekte
        )
        assert state.is_ready() is False

    def test_exhausted_not_ready(self):
        """Exhausted durumda asla ready degil."""
        state = SettlementRetryState(
            position_id="p1", claim_id="c1",
            exhausted=True, next_retry_at=0,
        )
        assert state.is_ready() is False


class TestSettlementRetryLifecycle:

    @pytest.mark.asyncio
    async def test_successful_first_try_no_retry(self):
        """Basarili ilk deneme -> retry state yok."""
        tracker, balance, claim_mgr, _, orch = _setup()
        _make_closed_position(tracker, balance)

        settled = await orch.process_settlements()
        assert settled == 1
        assert orch.pending_retry_count == 0

    @pytest.mark.asyncio
    async def test_failed_settlement_enters_retry(self):
        """Basarisiz settlement retry state olusturur."""
        tracker, balance, claim_mgr, _, orch = _setup(paper=False)
        _make_closed_position(tracker, balance)

        # Live mode + guard = settlement basarisiz
        settled = await orch.process_settlements()
        assert settled == 0
        assert orch.pending_retry_count == 1
        assert orch.has_pending_settlements() is True

    @pytest.mark.asyncio
    async def test_retry_succeeds_after_mode_switch(self):
        """Retry basarili olunca retry state temizlenir."""
        tracker, balance, claim_mgr, relayer, _ = _setup(paper=False)
        orch = SettlementOrchestrator(tracker, claim_mgr, relayer, paper_mode=False)
        pos = _make_closed_position(tracker, balance)

        # Ilk deneme basarisiz (live guard)
        await orch.process_settlements()
        assert orch.pending_retry_count == 1

        # Paper mode'a gecir (hem orch hem claim_mgr)
        orch._paper_mode = True
        claim_mgr._paper_mode = True
        for state in orch._retry_states.values():
            state.next_retry_at = time.time() - 1  # hemen retry

        settled = await orch.process_settlements()
        assert settled == 1
        assert orch.pending_retry_count == 0

    @pytest.mark.asyncio
    async def test_retry_not_ready_skipped(self):
        """Retry zamani gelmemis pozisyon atlanir."""
        tracker, balance, claim_mgr, relayer, _ = _setup(paper=False)
        orch = SettlementOrchestrator(tracker, claim_mgr, relayer, paper_mode=False)
        _make_closed_position(tracker, balance)

        await orch.process_settlements()
        assert orch.pending_retry_count == 1

        # Retry zamani henuz gelmedi (next_retry_at gelecekte)
        settled = await orch.process_settlements()
        assert settled == 0
        assert orch.pending_retry_count == 1  # hala bekliyor

    @pytest.mark.asyncio
    async def test_retry_exhausted_marked_failed(self):
        """Max retry asilinca exhausted=True ve retry state temizlenir."""
        tracker, balance, claim_mgr, relayer, _ = _setup(paper=False)
        orch = SettlementOrchestrator(tracker, claim_mgr, relayer, paper_mode=False)
        _make_closed_position(tracker, balance)

        # Ilk deneme
        await orch.process_settlements()
        assert orch.pending_retry_count == 1

        # Max retry'a getir — schedule_next exhausted yapar
        states = list(orch._retry_states.values())
        for state in states:
            state.attempt_count = CLAIM_REDEEM_MAX_RETRIES - 1
            state.next_retry_at = time.time() - 1  # zamani gecmis

        # Retry denenir, relayer basarisiz, schedule_next() exhausted yapar
        await orch.process_settlements()
        # Exhausted state temizlendi
        assert orch.pending_retry_count == 0

    @pytest.mark.asyncio
    async def test_multiple_positions_independent_retry(self):
        """Birden fazla pozisyon bagimsiz retry."""
        tracker, balance, claim_mgr, relayer, _ = _setup(paper=False)
        orch = SettlementOrchestrator(tracker, claim_mgr, relayer, paper_mode=False)
        pos1 = _make_closed_position(tracker, balance, asset="BTC")
        pos2 = _make_closed_position(tracker, balance, asset="ETH")

        await orch.process_settlements()
        assert orch.pending_retry_count == 2


class TestPendingSettlementTradeBlock:

    @pytest.mark.asyncio
    async def test_has_pending_settlements_during_retry(self):
        """Retry surecinde has_pending_settlements=True."""
        tracker, balance, claim_mgr, relayer, _ = _setup(paper=False)
        orch = SettlementOrchestrator(tracker, claim_mgr, relayer, paper_mode=False)
        _make_closed_position(tracker, balance)

        assert orch.has_pending_settlements() is False  # basta yok
        await orch.process_settlements()
        assert orch.has_pending_settlements() is True  # retry var

    @pytest.mark.asyncio
    async def test_no_pending_after_success(self):
        """Basarili settlement sonrasi pending yok."""
        tracker, balance, claim_mgr, _, orch = _setup()
        _make_closed_position(tracker, balance)

        await orch.process_settlements()
        assert orch.has_pending_settlements() is False

    @pytest.mark.asyncio
    async def test_pending_claims_blocks_new_trade(self):
        """Pending claim + wait_for_claim=True -> validator REJECT."""
        from backend.execution.order_validator import OrderValidator
        from backend.execution.order_intent import OrderIntent, OrderSide
        from backend.execution.models import ValidationStatus

        validator = OrderValidator()
        intent = OrderIntent(
            asset="BTC", side=OrderSide.UP, amount_usd=5.0,
            condition_id="0x1", token_id="tok1", dominant_price=0.55,
        )

        # Pending claim var + wait=True -> REJECT
        result = validator.validate(
            intent, available_balance=100.0,
            event_fill_count=0, event_max=5,
            open_position_count=0, bot_max=10,
            has_pending_claims=True, wait_for_claim_redeem=True,
        )
        assert result.status == ValidationStatus.REJECTED

    @pytest.mark.asyncio
    async def test_pending_claims_allowed_when_wait_false(self):
        """Pending claim + wait_for_claim=False -> VALID."""
        from backend.execution.order_validator import OrderValidator
        from backend.execution.order_intent import OrderIntent, OrderSide
        from backend.execution.models import ValidationStatus

        validator = OrderValidator()
        intent = OrderIntent(
            asset="BTC", side=OrderSide.UP, amount_usd=5.0,
            condition_id="0x1", token_id="tok1", dominant_price=0.55,
        )

        result = validator.validate(
            intent, available_balance=100.0,
            event_fill_count=0, event_max=5,
            open_position_count=0, bot_max=10,
            has_pending_claims=True, wait_for_claim_redeem=False,
        )
        assert result.status == ValidationStatus.VALID

    @pytest.mark.asyncio
    async def test_settlement_retry_keeps_trade_blocked(self):
        """Settlement retry surecinde claim PENDING -> trade blocked."""
        tracker, balance, claim_mgr, relayer, _ = _setup(paper=False)
        orch = SettlementOrchestrator(tracker, claim_mgr, relayer, paper_mode=False)
        _make_closed_position(tracker, balance)

        # Settlement basarisiz -> retry -> claim PENDING
        await orch.process_settlements()

        # Pending claim var
        assert claim_mgr.has_pending_claims() is True
        # Settlement de pending
        assert orch.has_pending_settlements() is True

    @pytest.mark.asyncio
    async def test_full_cycle_block_then_unblock(self):
        """Tam dongu: close -> settlement fail -> retry -> success -> trade unblock."""
        tracker, balance, claim_mgr, relayer, _ = _setup(paper=False)
        orch = SettlementOrchestrator(tracker, claim_mgr, relayer, paper_mode=False)
        pos = _make_closed_position(tracker, balance)

        # 1. Settlement basarisiz -> trade blocked
        await orch.process_settlements()
        assert orch.has_pending_settlements() is True
        assert claim_mgr.has_pending_claims() is True

        # 2. Paper mode'a gecir (hem orch hem claim_mgr) + retry zamani gecmise cek
        orch._paper_mode = True
        claim_mgr._paper_mode = True
        for state in orch._retry_states.values():
            state.next_retry_at = time.time() - 1

        # 3. Retry basarili
        settled = await orch.process_settlements()
        assert settled == 1

        # 4. Trade unblocked
        assert orch.has_pending_settlements() is False
        # Claim basarili oldugunda artik pending degil
        claims = claim_mgr.get_claims_by_position(pos.position_id)
        assert any(c.is_success for c in claims)


# ===================================================================
# RESOLUTION MODEL (v0.6.7)
# ===================================================================

class MockPTBFetcher:
    """PTBFetcher mock — PTB degerlerini condition_id bazli tutar."""
    def __init__(self):
        self._records = {}

    def set_ptb(self, condition_id, asset, value):
        from backend.ptb.models import PTBRecord
        rec = PTBRecord(condition_id=condition_id, asset=asset)
        rec.lock(value, "test_mock")
        self._records[condition_id] = rec

    def get_record(self, condition_id):
        return self._records.get(condition_id)


class MockCoinPriceClient:
    """CoinPriceClient mock — coin USD fiyatlarini tutar."""
    def __init__(self):
        self._prices = {}

    def set_price(self, coin, usd_price):
        self._prices[coin] = usd_price

    def get_usd_price(self, coin):
        return self._prices.get(coin, 0.0)


def _setup_with_resolution(ptb_value=67000.0, coin_usd=67500.0,
                            asset="BTC", condition_id="0x1"):
    """Resolution model testleri icin setup."""
    tracker = PositionTracker()
    balance = BalanceManager()
    balance.update(available=50.0)
    claim_mgr = ClaimManager(balance, paper_mode=True)
    relayer = RelayerClientWrapper()

    ptb = MockPTBFetcher()
    ptb.set_ptb(condition_id, asset, ptb_value)

    coin = MockCoinPriceClient()
    coin.set_price(asset, coin_usd)

    orch = SettlementOrchestrator(
        tracker, claim_mgr, relayer, paper_mode=True,
        ptb_fetcher=ptb, coin_price_client=coin,
    )
    return tracker, balance, claim_mgr, orch, ptb, coin


class TestResolutionModel:

    @pytest.mark.asyncio
    async def test_up_wins_when_coin_above_ptb(self):
        """coin_usd > ptb -> UP kazanir, UP pozisyon WON."""
        tracker, balance, claim_mgr, orch, _, _ = _setup_with_resolution(
            ptb_value=67000.0, coin_usd=67500.0,
        )
        # UP pozisyon ac ve kapat
        pos = _make_closed_position(tracker, balance, fill=0.85, exit_price=0.92)
        assert pos.side == "UP"

        await orch.process_settlements()
        claims = claim_mgr.get_claims_by_position(pos.position_id)
        assert claims[0].outcome == ClaimOutcome.REDEEMED_WON
        assert claims[0].claimed_amount_usdc > 0
        assert orch._last_resolution_method == "resolution"

    @pytest.mark.asyncio
    async def test_down_wins_when_coin_below_ptb(self):
        """coin_usd < ptb -> DOWN kazanir, UP pozisyon LOST."""
        tracker, balance, claim_mgr, orch, _, _ = _setup_with_resolution(
            ptb_value=67000.0, coin_usd=66500.0,
        )
        pos = _make_closed_position(tracker, balance, fill=0.85, exit_price=0.92)
        assert pos.side == "UP"

        await orch.process_settlements()
        claims = claim_mgr.get_claims_by_position(pos.position_id)
        # UP pozisyon ama DOWN kazandi -> LOST
        assert claims[0].outcome == ClaimOutcome.REDEEMED_LOST
        assert claims[0].claimed_amount_usdc == 0.0
        assert orch._last_resolution_method == "resolution"

    @pytest.mark.asyncio
    async def test_down_wins_when_coin_equals_ptb(self):
        """coin_usd == ptb -> DOWN kazanir (esitlikte DOWN)."""
        tracker, balance, claim_mgr, orch, _, _ = _setup_with_resolution(
            ptb_value=67000.0, coin_usd=67000.0,
        )
        pos = _make_closed_position(tracker, balance, fill=0.85, exit_price=0.92)

        await orch.process_settlements()
        claims = claim_mgr.get_claims_by_position(pos.position_id)
        assert claims[0].outcome == ClaimOutcome.REDEEMED_LOST  # UP, ama DOWN kazandi
        assert orch._last_resolution_method == "resolution"

    @pytest.mark.asyncio
    async def test_resolution_independent_of_pnl(self):
        """Resolution PnL'den bagimsiz — pozisyon kar'da kapansa bile kazanan taraf belirleyici."""
        tracker, balance, claim_mgr, orch, _, _ = _setup_with_resolution(
            ptb_value=67000.0, coin_usd=66500.0,  # DOWN kazanir
        )
        # UP pozisyon, kar'da kapanmis (fill=0.85, exit=0.92 -> PnL pozitif)
        pos = _make_closed_position(tracker, balance, fill=0.85, exit_price=0.92)
        assert pos.net_realized_pnl > 0  # PnL pozitif

        await orch.process_settlements()
        claims = claim_mgr.get_claims_by_position(pos.position_id)
        # PnL pozitif olsa bile, DOWN kazandigi icin UP pozisyon LOST
        assert claims[0].outcome == ClaimOutcome.REDEEMED_LOST
        assert orch._last_resolution_method == "resolution"

    @pytest.mark.asyncio
    async def test_pnl_fallback_when_no_ptb(self):
        """PTB yoksa PnL fallback kullanilir."""
        tracker, balance, claim_mgr, _, orch = _setup()  # PTB/coin inject yok
        pos = _make_closed_position(tracker, balance, fill=0.85, exit_price=0.92)

        await orch.process_settlements()
        claims = claim_mgr.get_claims_by_position(pos.position_id)
        assert claims[0].outcome == ClaimOutcome.REDEEMED_WON  # PnL > 0
        assert orch._last_resolution_method == "pnl_fallback"

    @pytest.mark.asyncio
    async def test_pnl_fallback_when_no_coin_price(self):
        """Coin USD fiyati yoksa PnL fallback."""
        tracker = PositionTracker()
        balance = BalanceManager()
        balance.update(available=50.0)
        claim_mgr = ClaimManager(balance, paper_mode=True)
        relayer = RelayerClientWrapper()

        ptb = MockPTBFetcher()
        ptb.set_ptb("0x1", "BTC", 67000.0)
        # coin_price_client = None

        orch = SettlementOrchestrator(
            tracker, claim_mgr, relayer, paper_mode=True,
            ptb_fetcher=ptb, coin_price_client=None,
        )
        pos = _make_closed_position(tracker, balance)
        await orch.process_settlements()
        assert orch._last_resolution_method == "pnl_fallback"

    @pytest.mark.asyncio
    async def test_balance_correct_on_resolution_win(self):
        """Resolution WON -> balance artar."""
        tracker, balance, claim_mgr, orch, _, _ = _setup_with_resolution(
            ptb_value=67000.0, coin_usd=67500.0,
        )
        before = balance.available_balance
        _make_closed_position(tracker, balance, fill=0.85, exit_price=0.92)
        await orch.process_settlements()
        assert balance.available_balance > before

    @pytest.mark.asyncio
    async def test_balance_unchanged_on_resolution_loss(self):
        """Resolution LOST -> balance degismez."""
        tracker, balance, claim_mgr, orch, _, _ = _setup_with_resolution(
            ptb_value=67000.0, coin_usd=66500.0,
        )
        _make_closed_position(tracker, balance, fill=0.85, exit_price=0.92)
        before = balance.available_balance
        await orch.process_settlements()
        assert balance.available_balance == before  # LOST -> $0


# ===================================================================
# BOUNDARY
# ===================================================================

class TestSettlementBoundaries:

    def test_no_strategy_coupling(self):
        import backend.orchestrator.settlement as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "strategy" not in line
            assert "rule" not in line

    def test_relayer_separate_from_clob(self):
        import backend.execution.relayer_client_wrapper as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "clob_client" not in line
            assert "order" not in line
