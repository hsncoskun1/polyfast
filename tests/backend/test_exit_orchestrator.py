"""ExitOrchestrator tests -- v0.6.9."""

import pytest
from backend.orchestrator.exit_orchestrator import ExitOrchestrator
from backend.orchestrator.settlement import SettlementOrchestrator
from backend.execution.exit_evaluator import ExitEvaluator
from backend.execution.exit_executor import ExitExecutor
from backend.execution.position_tracker import PositionTracker
from backend.execution.position_record import PositionState
from backend.execution.balance_manager import BalanceManager
from backend.execution.claim_manager import ClaimManager, ClaimOutcome, ClaimStatus
from backend.execution.close_reason import CloseReason
from backend.execution.relayer_client_wrapper import RelayerClientWrapper


def _setup(tp_pct=5.0, sl_pct=3.0, fs_time=True, fs_time_sec=30):
    tracker = PositionTracker()
    balance = BalanceManager()
    balance.update(available=100.0)
    evaluator = ExitEvaluator(
        tp_pct=tp_pct, sl_pct=sl_pct,
        force_sell_time_enabled=fs_time, force_sell_time_seconds=fs_time_sec,
    )
    # v0.9.1: exit_evaluator executor'a inject — TP reevaluate tek noktada
    executor = ExitExecutor(tracker, balance, exit_evaluator=evaluator, paper_mode=True)
    claim_mgr = ClaimManager(balance, paper_mode=True)
    relayer = RelayerClientWrapper()
    settlement = SettlementOrchestrator(tracker, claim_mgr, relayer, paper_mode=True)
    orch = ExitOrchestrator(tracker, evaluator, executor, settlement, claim_mgr)
    return tracker, balance, evaluator, executor, settlement, claim_mgr, orch


def _open_position(tracker, fill=0.85, asset="BTC"):
    pos = tracker.create_pending(asset, "UP", "0x1", "tok1", 5.0)
    tracker.confirm_fill(pos.position_id, fill_price=fill)
    return pos


class TestExitOrchestratorTP:

    @pytest.mark.asyncio
    async def test_tp_trigger_and_close_single_cycle(self):
        """TP tetik + close tek cycle'da. Settlement YOK — token satildi."""
        tracker, balance, _, _, _, claim_mgr, orch = _setup(tp_pct=5.0)
        pos = _open_position(tracker)

        result = await orch.run_cycle(
            current_prices={"BTC": 0.92},
            remaining_seconds={"BTC": 200},
        )
        assert result["triggers"] == 1
        assert result["closes"] == 1
        assert result["settlements"] == 0  # token satildi, redeem yok
        assert pos.is_closed
        assert pos.was_sold is True

    @pytest.mark.asyncio
    async def test_tp_reevaluate_cancels_close(self):
        """TP tetiklendi ama fiyat geri cekildiyse close iptal edilir.

        Senaryo: TP tetikle (manuel request_close ile), sonra fiyat dusur.
        ExitOrchestrator closing_requested pozisyonu reevaluate eder.
        """
        tracker, balance, _, _, _, _, orch = _setup(tp_pct=5.0)
        pos = _open_position(tracker)

        # TP'yi manuel request_close ile tetikle (evaluator'dan ayri)
        tracker.request_close(pos.position_id, CloseReason.TAKE_PROFIT)
        assert pos.state == PositionState.CLOSING_REQUESTED

        # Fiyat geri cekildi — TP artik saglanmiyor
        await orch.run_cycle(
            current_prices={"BTC": 0.86},
            remaining_seconds={"BTC": 200},
        )
        assert pos.state == PositionState.OPEN_CONFIRMED  # geri dondu


class TestExitOrchestratorSL:

    @pytest.mark.asyncio
    async def test_sl_trigger_and_close(self):
        """SL tetik -> close tek cycle'da, latch."""
        tracker, balance, _, _, _, _, orch = _setup(sl_pct=3.0)
        pos = _open_position(tracker, fill=0.85)

        # Fiyat SL'yi tetikleyecek seviyede — tek cycle'da tetik+close
        result = await orch.run_cycle(
            current_prices={"BTC": 0.80},
            remaining_seconds={"BTC": 200},
        )
        assert result["triggers"] == 1
        assert result["closes"] == 1
        assert pos.is_closed
        assert pos.close_reason == CloseReason.STOP_LOSS


class TestExitOrchestratorForceSell:

    @pytest.mark.asyncio
    async def test_force_sell_time(self):
        """Force sell time tetik."""
        tracker, balance, _, _, _, _, orch = _setup(fs_time=True, fs_time_sec=30)
        pos = _open_position(tracker)

        # Time = 25 saniye kaldi (< 30)
        result = await orch.run_cycle(
            current_prices={"BTC": 0.86},
            remaining_seconds={"BTC": 25},
        )
        assert result["triggers"] == 1
        assert pos.close_reason == CloseReason.FORCE_SELL


class TestExitOrchestratorSettlement:

    @pytest.mark.asyncio
    async def test_tp_close_no_settlement(self):
        """TP close -> token satildi -> settlement YOK."""
        tracker, balance, _, _, _, claim_mgr, orch = _setup()
        pos = _open_position(tracker)

        result = await orch.run_cycle(current_prices={"BTC": 0.92}, remaining_seconds={"BTC": 200})
        assert result["triggers"] == 1
        assert result["closes"] == 1
        assert result["settlements"] == 0  # was_sold -> no redeem
        assert pos.is_closed
        assert pos.was_sold is True

        claims = claim_mgr.get_claims_by_position(pos.position_id)
        assert len(claims) == 0  # satis ile kapandi, claim olusturmadi


class TestExternalReconciliation:

    @pytest.mark.asyncio
    async def test_mark_externally_settled(self):
        """mark_externally_settled pending claim'i kapatir."""
        balance = BalanceManager()
        balance.update(available=100.0)
        claim_mgr = ClaimManager(balance, paper_mode=True)

        claim = claim_mgr.create_claim("0x1", "pos1", "BTC", "UP")
        assert claim.is_pending

        result = claim_mgr.mark_externally_settled(claim.claim_id)
        assert result is True
        assert claim.claim_status == ClaimStatus.SUCCESS
        assert claim.last_error == "external_settlement_detected"

    @pytest.mark.asyncio
    async def test_already_settled_not_error(self):
        """Zaten settled claim'e mark_externally_settled hata degil."""
        balance = BalanceManager()
        balance.update(available=100.0)
        claim_mgr = ClaimManager(balance, paper_mode=True)

        claim = claim_mgr.create_claim("0x1", "pos1", "BTC", "UP")
        await claim_mgr.execute_redeem(claim.claim_id, won=True, payout_amount=5.0)
        assert claim.is_success

        result = claim_mgr.mark_externally_settled(claim.claim_id)
        assert result is True  # hata degil, zaten settled

    @pytest.mark.asyncio
    async def test_reconcile_clears_stuck_pending(self):
        """Pending ama retry'da olmayan claim reconcile ile kapanir."""
        tracker, balance, _, _, settlement, claim_mgr, orch = _setup()

        # Pozisyon ac, kapat, settlement yap (paper mode basarili)
        pos = _open_position(tracker)
        tracker.request_close(pos.position_id, CloseReason.TAKE_PROFIT)
        tracker.confirm_close(pos.position_id, exit_fill_price=0.92)

        # Manuel claim olustur (settlement disinda — stuck senaryo)
        stuck_claim = claim_mgr.create_claim("0x2", "pos_stuck", "ETH", "UP")
        assert stuck_claim.is_pending

        # Reconcile — stuck claim retry'da degil -> kapanmali
        result = await orch.run_cycle(current_prices={}, remaining_seconds={})
        assert result["reconciled"] == 1

        # Stuck claim artik pending degil
        assert not stuck_claim.is_pending

    @pytest.mark.asyncio
    async def test_retry_not_reconciled(self):
        """Retry'da olan pending claim reconcile EDILMEZ."""
        tracker = PositionTracker()
        balance = BalanceManager()
        balance.update(available=100.0)
        claim_mgr = ClaimManager(balance, paper_mode=False)
        relayer = RelayerClientWrapper()

        from backend.execution.clob_client_wrapper import MarketResolution

        class MockClob:
            async def get_market_resolution(self, cid):
                return MarketResolution(condition_id=cid, closed=True, resolved=True, winning_side="UP")

        settlement = SettlementOrchestrator(
            tracker, claim_mgr, relayer, paper_mode=False,
            clob_client=MockClob(),
        )
        evaluator = ExitEvaluator()
        executor = ExitExecutor(tracker, balance, paper_mode=True)
        orch = ExitOrchestrator(tracker, evaluator, executor, settlement, claim_mgr)

        # Pozisyon ac ve EXPIRY ile kapat (token elde, redeem gerekli)
        pos = _open_position(tracker)
        tracker.request_close(pos.position_id, CloseReason.EXPIRY)
        tracker.confirm_close(pos.position_id, exit_fill_price=0.92)
        assert pos.needs_redeem is True

        # Settlement basarisiz -> retry'a girer
        await settlement.process_settlements()
        assert settlement.pending_retry_count == 1

        # Reconcile — retry'da olan claim reconcile edilmemeli
        reconciled = await orch._reconcile_external()
        assert reconciled == 0


class TestExitOrchestratorBoundaries:

    def test_no_strategy_coupling(self):
        import backend.orchestrator.exit_orchestrator as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "strategy" not in line
            assert "rule_engine" not in line
            assert "evaluation_context" not in line

    def test_coordinator_not_state_authority(self):
        """ExitOrchestrator state degistirmez — PositionTracker'a delege eder."""
        import backend.orchestrator.exit_orchestrator as mod
        source = open(mod.__file__, encoding="utf-8").read()
        # Direct state assignment olmamali
        assert "pos.state =" not in source or "pos.state ==" in source
