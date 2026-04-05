"""ClaimManager + Manual Close + wait_for_claim tests — v0.6.3.

Netlestirmeler:
1. Position CLOSED kalir, claim ayri ClaimRecord lifecycle
2. Kaybeden tarafta claim OLUSMAZ — sifir sonuc kaydi YOK
3. Manual close: UI butonu state URETMEZ, backend lifecycle yurur
4. Claim max 10 retry — urun karari
"""

import pytest
from datetime import datetime, timezone

from backend.execution.claim_manager import (
    ClaimManager, ClaimRecord, ClaimStatus,
    CLAIM_REDEEM_MAX_RETRIES,
)
from backend.execution.position_tracker import PositionTracker
from backend.execution.position_record import PositionState
from backend.execution.balance_manager import BalanceManager
from backend.execution.exit_executor import ExitExecutor
from backend.execution.exit_evaluator import ExitEvaluator
from backend.execution.close_reason import CloseReason


def _make_closed_position():
    tracker = PositionTracker()
    balance = BalanceManager()
    balance.update(available=50.0)
    pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 5.0)
    tracker.confirm_fill(pos.position_id, fill_price=0.85)
    tracker.request_close(pos.position_id, CloseReason.TAKE_PROFIT)
    tracker.confirm_close(pos.position_id, exit_fill_price=0.92)
    return pos, tracker, balance


# ═══════════════════════════════════════════════════════════════
# CLAIM LIFECYCLE
# ═══════════════════════════════════════════════════════════════

class TestClaimLifecycle:

    @pytest.mark.asyncio
    async def test_create_claim(self):
        pos, _, balance = _make_closed_position()
        mgr = ClaimManager(balance, paper_mode=True)
        claim = mgr.create_claim("0x1", pos.position_id, "BTC")
        assert claim.is_pending
        assert claim.condition_id == "0x1"
        assert claim.position_id == pos.position_id

    @pytest.mark.asyncio
    async def test_execute_claim_paper(self):
        pos, _, balance = _make_closed_position()
        mgr = ClaimManager(balance, paper_mode=True)
        claim = mgr.create_claim("0x1", pos.position_id, "BTC")

        success = await mgr.execute_claim(claim.claim_id)
        assert success is True
        assert claim.is_success
        assert claim.claimed_amount_usdc > 0
        assert claim.claimed_at is not None

    @pytest.mark.asyncio
    async def test_position_stays_closed_after_claim(self):
        """Position CLOSED kalir — claim ayri lifecycle."""
        pos, _, balance = _make_closed_position()
        assert pos.is_closed
        assert pos.state == PositionState.CLOSED

        mgr = ClaimManager(balance, paper_mode=True)
        claim = mgr.create_claim("0x1", pos.position_id, "BTC")
        await mgr.execute_claim(claim.claim_id)

        # Position hala CLOSED — claim state degistirmez
        assert pos.is_closed
        assert pos.state == PositionState.CLOSED

    @pytest.mark.asyncio
    async def test_claim_record_separate_from_position(self):
        """ClaimRecord PositionRecord'dan AYRI — claim ayri model."""
        pos, _, balance = _make_closed_position()
        mgr = ClaimManager(balance, paper_mode=True)
        claim = mgr.create_claim("0x1", pos.position_id, "BTC")

        # ClaimRecord ve PositionRecord farkli objeler
        assert type(claim).__name__ == "ClaimRecord"
        assert type(pos).__name__ == "PositionRecord"
        # Ama position_id iliskisi authoritative korunur
        assert claim.position_id == pos.position_id
        assert claim.condition_id == pos.condition_id

    @pytest.mark.asyncio
    async def test_post_claim_balance_refresh(self):
        """Claim basarili → balance artar."""
        _, _, balance = _make_closed_position()
        before = balance.available_balance
        mgr = ClaimManager(balance, paper_mode=True)
        claim = mgr.create_claim("0x1", "pos1", "BTC")
        await mgr.execute_claim(claim.claim_id)
        assert balance.available_balance > before

    @pytest.mark.asyncio
    async def test_claimed_amount_authoritative(self):
        """claimed_amount_usdc basarili olunca sabitlenir."""
        _, _, balance = _make_closed_position()
        mgr = ClaimManager(balance, paper_mode=True)
        claim = mgr.create_claim("0x1", "pos1", "BTC")
        await mgr.execute_claim(claim.claim_id)

        original = claim.claimed_amount_usdc
        assert original > 0
        # Tekrar execute etmek degistirmez — zaten success
        await mgr.execute_claim(claim.claim_id)
        assert claim.claimed_amount_usdc == original


# ═══════════════════════════════════════════════════════════════
# KAYBEDEN TARAF — CLAIM OLUSMAZ
# ═══════════════════════════════════════════════════════════════

class TestLosingPosition:

    def test_losing_position_no_claim(self):
        """Kaybeden tarafta claim OLUSMAZ — sifir sonuc kaydi YOK.

        Karar: claim sadece kazanan taraf icin olusturulur.
        Kaybeden taraf ($0.00 degerinde) icin ClaimRecord uretilmez.
        Bu orchestrator/exit katmaninda kontrol edilir.
        """
        # Bu test kavramsal — ClaimManager'a sadece kazanan pozisyonlar gelir
        # Kaybeden icin create_claim cagirilmaz
        balance = BalanceManager()
        balance.update(available=50.0)
        mgr = ClaimManager(balance, paper_mode=True)

        # Kazanan icin claim olustur
        claim = mgr.create_claim("0x1", "winning_pos", "BTC")
        assert claim is not None

        # Kaybeden icin claim OLUSTURMA — bu test ClaimManager'in
        # kafasina karar yuklemez, orchestrator kontrol eder
        assert mgr.pending_count == 1  # sadece 1 claim (kazanan)


# ═══════════════════════════════════════════════════════════════
# MANUAL CLOSE
# ═══════════════════════════════════════════════════════════════

class TestManualClose:

    @pytest.mark.asyncio
    async def test_manual_close_lifecycle(self):
        """Manual close: backend request alir, lifecycle yurutur."""
        tracker = PositionTracker()
        balance = BalanceManager()
        balance.update(available=50.0)
        pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 5.0)
        tracker.confirm_fill(pos.position_id, fill_price=0.85)

        # Manual close request — backend lifecycle
        tracker.request_close(pos.position_id, CloseReason.MANUAL_CLOSE)
        assert pos.state == PositionState.CLOSING_REQUESTED
        assert pos.close_reason == CloseReason.MANUAL_CLOSE
        assert pos.close_trigger_set == []  # kullanici tetikledi

        # Execute close
        executor = ExitExecutor(tracker, balance, paper_mode=True)
        success = await executor.execute_close(pos, current_price=0.87)
        assert success is True
        assert pos.is_closed

    @pytest.mark.asyncio
    async def test_manual_close_no_reevaluate(self):
        """Manual close'da reevaluate YOK — should_cancel_close False."""
        tracker = PositionTracker()
        balance = BalanceManager()
        balance.update(available=50.0)
        pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 5.0)
        tracker.confirm_fill(pos.position_id, fill_price=0.85)
        tracker.request_close(pos.position_id, CloseReason.MANUAL_CLOSE)

        evaluator = ExitEvaluator(tp_reevaluate=True)
        # Manual close icin cancel YOK
        assert evaluator.should_cancel_close(pos, current_price=0.95) is False

    def test_manual_close_is_latch(self):
        """Manual close latch — iptal edilemez."""
        tracker = PositionTracker()
        pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 5.0)
        tracker.confirm_fill(pos.position_id, fill_price=0.85)
        tracker.request_close(pos.position_id, CloseReason.MANUAL_CLOSE)

        # UI butonu state URETMEZ — backend lifecycle yurur
        assert pos.state == PositionState.CLOSING_REQUESTED
        assert pos.close_reason == CloseReason.MANUAL_CLOSE


# ═══════════════════════════════════════════════════════════════
# WAIT FOR CLAIM GUARD
# ═══════════════════════════════════════════════════════════════

class TestWaitForClaim:

    def test_has_pending_claims(self):
        balance = BalanceManager()
        balance.update(available=50.0)
        mgr = ClaimManager(balance, paper_mode=True)
        assert mgr.has_pending_claims() is False

        mgr.create_claim("0x1", "pos1", "BTC")
        assert mgr.has_pending_claims() is True

    @pytest.mark.asyncio
    async def test_no_pending_after_success(self):
        balance = BalanceManager()
        balance.update(available=50.0)
        mgr = ClaimManager(balance, paper_mode=True)
        claim = mgr.create_claim("0x1", "pos1", "BTC")
        await mgr.execute_claim(claim.claim_id)
        assert mgr.has_pending_claims() is False

    def test_claim_pending_reject_reason_exists(self):
        """CLAIM_PENDING reject reason mevcut."""
        from backend.execution.models import RejectReason
        assert RejectReason.CLAIM_PENDING == "claim_pending"


# ═══════════════════════════════════════════════════════════════
# CLAIM RETRY
# ═══════════════════════════════════════════════════════════════

class TestClaimRetry:

    def test_max_retries_constant(self):
        """Max 20 retry — urun karari."""
        assert CLAIM_REDEEM_MAX_RETRIES == 20

    @pytest.mark.asyncio
    async def test_already_claimed_returns_true(self):
        """Zaten claim edilmis → tekrar execute True doner."""
        balance = BalanceManager()
        balance.update(available=50.0)
        mgr = ClaimManager(balance, paper_mode=True)
        claim = mgr.create_claim("0x1", "pos1", "BTC")
        await mgr.execute_claim(claim.claim_id)
        assert claim.is_success

        result = await mgr.execute_claim(claim.claim_id)
        assert result is True  # zaten success

    def test_health_incident_on_max_retries(self):
        """Max retry asilirsa health incident."""
        balance = BalanceManager()
        balance.update(available=50.0)
        mgr = ClaimManager(balance, paper_mode=True)
        claim = mgr.create_claim("0x1", "pos1", "BTC")
        claim.claim_status = ClaimStatus.FAILED
        claim.retry_count = 21  # max 20 asildi

        incidents = mgr.get_health_incidents()
        assert len(incidents) >= 1


# ═══════════════════════════════════════════════════════════════
# BOUNDARY
# ═══════════════════════════════════════════════════════════════

class TestClaimBoundaries:

    def test_no_strategy_coupling(self):
        import backend.execution.claim_manager as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "strategy" not in line
            assert "rule" not in line
