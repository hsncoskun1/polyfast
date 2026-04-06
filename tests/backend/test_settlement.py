"""Settlement + RelayerWrapper tests — v0.6.5."""

import pytest
from backend.orchestrator.settlement import SettlementOrchestrator
from backend.execution.position_tracker import PositionTracker
from backend.execution.claim_manager import ClaimManager, ClaimOutcome
from backend.execution.balance_manager import BalanceManager
from backend.execution.close_reason import CloseReason
from backend.execution.relayer_client_wrapper import (
    RelayerClientWrapper, LIVE_SETTLEMENT_ENABLED,
)


def _make_closed_position(tracker, balance, fill=0.85, exit=0.92, reason=CloseReason.TAKE_PROFIT):
    pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 5.0)
    tracker.confirm_fill(pos.position_id, fill_price=fill)
    tracker.request_close(pos.position_id, reason)
    tracker.confirm_close(pos.position_id, exit_fill_price=exit)
    return pos


# ═══════════════════════════════════════════════════════════════
# RELAYER WRAPPER
# ═══════════════════════════════════════════════════════════════

class TestRelayerWrapper:

    def test_live_settlement_guard(self):
        """LIVE_SETTLEMENT_ENABLED=False → gercek TX cikmaz."""
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
        assert result is True  # paper placeholder

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


# ═══════════════════════════════════════════════════════════════
# SETTLEMENT ORCHESTRATION
# ═══════════════════════════════════════════════════════════════

class TestSettlementOrchestrator:

    @pytest.mark.asyncio
    async def test_settle_winning_position(self):
        """Kazanan pozisyon: redeem → USDC, outcome=REDEEMED_WON."""
        tracker = PositionTracker()
        balance = BalanceManager()
        balance.update(available=50.0)
        claim_mgr = ClaimManager(balance, paper_mode=True)
        relayer = RelayerClientWrapper()

        # TP ile karda kapat
        pos = _make_closed_position(tracker, balance, fill=0.85, exit=0.92)
        assert pos.net_realized_pnl > 0

        orch = SettlementOrchestrator(tracker, claim_mgr, relayer, paper_mode=True)
        settled = await orch.process_settlements()

        assert settled == 1
        claims = claim_mgr.get_claims_by_position(pos.position_id)
        assert len(claims) == 1
        assert claims[0].outcome == ClaimOutcome.REDEEMED_WON
        assert claims[0].claimed_amount_usdc > 0

    @pytest.mark.asyncio
    async def test_settle_losing_position(self):
        """Kaybeden pozisyon: redeem → $0, outcome=REDEEMED_LOST."""
        tracker = PositionTracker()
        balance = BalanceManager()
        balance.update(available=50.0)
        claim_mgr = ClaimManager(balance, paper_mode=True)
        relayer = RelayerClientWrapper()

        # SL ile zararda kapat
        pos = _make_closed_position(tracker, balance, fill=0.85, exit=0.78, reason=CloseReason.STOP_LOSS)
        assert pos.net_realized_pnl < 0

        orch = SettlementOrchestrator(tracker, claim_mgr, relayer, paper_mode=True)
        settled = await orch.process_settlements()

        assert settled == 1
        claims = claim_mgr.get_claims_by_position(pos.position_id)
        assert len(claims) == 1
        assert claims[0].outcome == ClaimOutcome.REDEEMED_LOST
        assert claims[0].claimed_amount_usdc == 0.0

    @pytest.mark.asyncio
    async def test_already_settled_skipped(self):
        """Zaten settled pozisyon tekrar settle edilmez."""
        tracker = PositionTracker()
        balance = BalanceManager()
        balance.update(available=50.0)
        claim_mgr = ClaimManager(balance, paper_mode=True)
        relayer = RelayerClientWrapper()

        pos = _make_closed_position(tracker, balance)
        orch = SettlementOrchestrator(tracker, claim_mgr, relayer, paper_mode=True)

        # İlk settlement
        settled1 = await orch.process_settlements()
        assert settled1 == 1

        # İkinci — zaten settled, tekrar denemez
        settled2 = await orch.process_settlements()
        assert settled2 == 0

    @pytest.mark.asyncio
    async def test_open_position_not_settled(self):
        """Acik pozisyon settle edilmez — sadece CLOSED pozisyonlar."""
        tracker = PositionTracker()
        balance = BalanceManager()
        balance.update(available=50.0)
        claim_mgr = ClaimManager(balance, paper_mode=True)
        relayer = RelayerClientWrapper()

        # Acik pozisyon — closed degil
        pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 5.0)
        tracker.confirm_fill(pos.position_id, fill_price=0.85)

        orch = SettlementOrchestrator(tracker, claim_mgr, relayer, paper_mode=True)
        settled = await orch.process_settlements()
        assert settled == 0

    @pytest.mark.asyncio
    async def test_balance_increases_on_win(self):
        """Kazanan settlement sonrasi balance artar."""
        tracker = PositionTracker()
        balance = BalanceManager()
        balance.update(available=50.0)
        claim_mgr = ClaimManager(balance, paper_mode=True)
        relayer = RelayerClientWrapper()

        before = balance.available_balance
        pos = _make_closed_position(tracker, balance, fill=0.85, exit=0.92)
        orch = SettlementOrchestrator(tracker, claim_mgr, relayer, paper_mode=True)
        await orch.process_settlements()

        assert balance.available_balance > before

    @pytest.mark.asyncio
    async def test_balance_unchanged_on_loss(self):
        """Kaybeden settlement sonrasi balance degismez (redeem $0)."""
        tracker = PositionTracker()
        balance = BalanceManager()
        balance.update(available=50.0)
        claim_mgr = ClaimManager(balance, paper_mode=True)
        relayer = RelayerClientWrapper()

        pos = _make_closed_position(tracker, balance, fill=0.85, exit=0.78, reason=CloseReason.STOP_LOSS)
        before = balance.available_balance
        orch = SettlementOrchestrator(tracker, claim_mgr, relayer, paper_mode=True)
        await orch.process_settlements()

        assert balance.available_balance == before  # $0 payout → degismez


# ═══════════════════════════════════════════════════════════════
# BOUNDARY
# ═══════════════════════════════════════════════════════════════

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
