"""FAZ 6 INTEGRATION E2E -- uctan uca exit + claim/redeem + reconciliation.

Butun Faz 6 akis halkalarini tek akista dogrular:
1. Entry (paper fill)
2. TP / SL / Force Sell / Manual Close tetik + close
3. Close execution
4. Settlement (resolution-based)
5. Pending settlement trade block
6. External manual settlement reconciliation
7. Idempotent davranis
8. Balance tutarliligi

Gercek para/live TX YOK -- paper mode.

Calistirma:
    python tools/faz6_integration_e2e.py
"""

import asyncio
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.execution.position_tracker import PositionTracker
from backend.execution.position_record import PositionState
from backend.execution.balance_manager import BalanceManager
from backend.execution.claim_manager import ClaimManager, ClaimOutcome, ClaimStatus
from backend.execution.close_reason import CloseReason, ForceSellTrigger
from backend.execution.exit_evaluator import ExitEvaluator
from backend.execution.exit_executor import ExitExecutor
from backend.execution.order_validator import OrderValidator
from backend.execution.order_intent import OrderIntent, OrderSide
from backend.execution.models import ValidationStatus, RejectReason
from backend.execution.relayer_client_wrapper import RelayerClientWrapper
from backend.execution.clob_client_wrapper import MarketResolution
from backend.orchestrator.settlement import SettlementOrchestrator
from backend.orchestrator.exit_orchestrator import ExitOrchestrator
from backend.ptb.models import PTBRecord

PASS = "\033[92mOK\033[0m"
FAIL = "\033[91mFAIL\033[0m"
HDR = "\033[96m"
RST = "\033[0m"

results = []


def check(label, condition, detail=""):
    tag = PASS if condition else FAIL
    extra = f"  ({detail})" if detail else ""
    print(f"  {tag} {label}{extra}")
    results.append((label, condition))


def header(title):
    print(f"\n{HDR}{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}{RST}")


class MockClobClient:
    def __init__(self, resolved=True, winning_side="UP"):
        self._resolved = resolved
        self._winning_side = winning_side

    async def get_market_resolution(self, cid):
        return MarketResolution(
            condition_id=cid, closed=self._resolved,
            resolved=self._resolved,
            winning_side=self._winning_side if self._resolved else "",
        )


def _full_setup(winning_side="UP"):
    tracker = PositionTracker()
    balance = BalanceManager()
    balance.update(available=100.0)
    evaluator = ExitEvaluator(
        tp_pct=5.0, sl_pct=3.0,
        force_sell_time_enabled=True, force_sell_time_seconds=30,
    )
    executor = ExitExecutor(tracker, balance, paper_mode=True)
    claim_mgr = ClaimManager(balance, paper_mode=True)
    relayer = RelayerClientWrapper()
    clob = MockClobClient(resolved=True, winning_side=winning_side)
    settlement = SettlementOrchestrator(
        tracker, claim_mgr, relayer, paper_mode=True, clob_client=clob,
    )
    orch = ExitOrchestrator(tracker, evaluator, executor, settlement, claim_mgr)
    validator = OrderValidator()
    return tracker, balance, claim_mgr, settlement, orch, validator


def _open_pos(tracker, fill=0.85, asset="BTC"):
    pos = tracker.create_pending(asset, "UP", "0x1", "tok1", 5.0)
    tracker.confirm_fill(pos.position_id, fill_price=fill)
    return pos


async def test_full_tp_cycle():
    header("1) FULL TP CYCLE: entry -> TP -> close (token satildi)")
    tracker, balance, claim_mgr, _, orch, _ = _full_setup(winning_side="UP")
    before = balance.available_balance
    pos = _open_pos(tracker)

    result = await orch.run_cycle(current_prices={"BTC": 0.92}, remaining_seconds={"BTC": 200})
    check("TP trigger fired", result["triggers"] == 1)
    check("Close executed", result["closes"] == 1)
    check("Settlement=0 (token satildi, redeem yok)", result["settlements"] == 0)
    check("Position closed", pos.is_closed)
    check("Close reason: TAKE_PROFIT", pos.close_reason == CloseReason.TAKE_PROFIT)
    check("was_sold=True (satis geliri balance'ta)", pos.was_sold is True)
    check("Balance increased (satis geliri)", balance.available_balance > before,
          f"${before:.2f} -> ${balance.available_balance:.2f}")


async def test_full_sl_cycle():
    header("2) FULL SL CYCLE: entry -> SL -> close (token satildi)")
    tracker, balance, claim_mgr, _, orch, _ = _full_setup(winning_side="DOWN")
    pos = _open_pos(tracker)

    result = await orch.run_cycle(current_prices={"BTC": 0.80}, remaining_seconds={"BTC": 200})
    check("SL trigger fired", result["triggers"] == 1)
    check("Position closed", pos.is_closed)
    check("Close reason: STOP_LOSS", pos.close_reason == CloseReason.STOP_LOSS)
    check("Settlement=0 (token satildi)", result["settlements"] == 0)
    check("was_sold=True", pos.was_sold is True)


async def test_full_force_sell_cycle():
    header("3) FULL FORCE SELL CYCLE: entry -> force sell time -> close")
    tracker, balance, claim_mgr, _, orch, _ = _full_setup(winning_side="DOWN")
    pos = _open_pos(tracker)

    result = await orch.run_cycle(current_prices={"BTC": 0.86}, remaining_seconds={"BTC": 25})
    check("Force sell trigger fired", result["triggers"] == 1)
    check("Position closed", pos.is_closed)
    check("Close reason: FORCE_SELL", pos.close_reason == CloseReason.FORCE_SELL)
    check("Settlement=0 (token satildi)", result["settlements"] == 0)


async def test_full_manual_close_cycle():
    header("4) FULL MANUAL CLOSE CYCLE: manual request -> close (token satildi)")
    tracker, balance, claim_mgr, _, orch, _ = _full_setup(winning_side="UP")
    pos = _open_pos(tracker)

    tracker.request_close(pos.position_id, CloseReason.MANUAL_CLOSE)
    result = await orch.run_cycle(current_prices={"BTC": 0.88}, remaining_seconds={"BTC": 200})
    check("Close executed", result["closes"] == 1)
    check("Position closed", pos.is_closed)
    check("Close reason: MANUAL_CLOSE", pos.close_reason == CloseReason.MANUAL_CLOSE)
    check("Settlement=0 (token satildi)", result["settlements"] == 0)


async def test_pending_trade_block():
    header("5) PENDING SETTLEMENT -> TRADE BLOCK")
    tracker = PositionTracker()
    balance = BalanceManager()
    balance.update(available=100.0)
    claim_mgr = ClaimManager(balance, paper_mode=False)  # live mode -> fail
    relayer = RelayerClientWrapper()
    clob = MockClobClient(resolved=True, winning_side="UP")
    settlement = SettlementOrchestrator(
        tracker, claim_mgr, relayer, paper_mode=False, clob_client=clob,
    )
    evaluator = ExitEvaluator()
    executor = ExitExecutor(tracker, balance, paper_mode=True)
    orch = ExitOrchestrator(tracker, evaluator, executor, settlement, claim_mgr)
    validator = OrderValidator()

    # EXPIRY ile kapat — token elde, redeem gerekli
    pos = _open_pos(tracker)
    tracker.request_close(pos.position_id, CloseReason.EXPIRY)
    tracker.confirm_close(pos.position_id, exit_fill_price=0.92)

    await settlement.process_settlements()
    check("has_pending_settlements=True", settlement.has_pending_settlements())
    check("has_pending_claims=True", claim_mgr.has_pending_claims())

    intent = OrderIntent(
        asset="ETH", side=OrderSide.UP, amount_usd=5.0,
        condition_id="0x2", token_id="tok2", dominant_price=0.55,
    )
    result = validator.validate(
        intent, available_balance=100.0,
        event_fill_count=0, event_max=5,
        open_position_count=0, bot_max=10,
        has_pending_claims=True, wait_for_claim_redeem=True,
    )
    check("Trade REJECTED (CLAIM_PENDING)", result.status == ValidationStatus.REJECTED)
    check("Reason: CLAIM_PENDING", result.reason == RejectReason.CLAIM_PENDING)


async def test_external_reconciliation():
    header("6) EXTERNAL RECONCILIATION: stuck pending -> close")
    tracker, balance, claim_mgr, _, orch, _ = _full_setup()

    # Stuck claim olustur (settlement disinda)
    stuck = claim_mgr.create_claim("0x99", "stuck_pos", "SOL", "UP")
    check("Stuck claim is pending", stuck.is_pending)

    result = await orch.run_cycle(current_prices={}, remaining_seconds={})
    check("Reconciled: 1", result["reconciled"] == 1)
    check("Stuck claim no longer pending", not stuck.is_pending)
    check("last_error = external_settlement_detected", stuck.last_error == "external_settlement_detected")


async def test_idempotent_settlement():
    header("7) IDEMPOTENT SETTLEMENT: EXPIRY redeem -> ikinci skip")
    tracker, balance, claim_mgr, settlement, orch, _ = _full_setup(winning_side="UP")

    # EXPIRY ile kapat — token elde, redeem gerekli
    pos = _open_pos(tracker)
    tracker.request_close(pos.position_id, CloseReason.EXPIRY)
    tracker.confirm_close(pos.position_id, exit_fill_price=0.92)

    r1 = await orch.run_cycle(current_prices={}, remaining_seconds={})
    check("First cycle: settlement=1", r1["settlements"] == 1)
    b1 = balance.available_balance

    r2 = await orch.run_cycle(current_prices={}, remaining_seconds={})
    check("Second cycle: settlement=0 (skip)", r2["settlements"] == 0)
    check("Balance unchanged", balance.available_balance == b1)


async def test_balance_consistency():
    header("8) BALANCE CONSISTENCY: close = satis geliri ONLY (cift ekleme YOK)")
    tracker, balance, claim_mgr, _, orch, _ = _full_setup(winning_side="UP")

    start_balance = balance.available_balance
    pos = _open_pos(tracker)

    await orch.run_cycle(current_prices={"BTC": 0.92}, remaining_seconds={"BTC": 200})

    # TP close = token satildi. Balance = start + exit_usdc. Settlement payout YOK.
    exit_usdc = pos.net_exit_usdc
    expected = start_balance + exit_usdc

    check("Balance = start + exit_usdc (settlement payout YOK)",
          abs(balance.available_balance - expected) < 0.01,
          f"${start_balance:.2f} + ${exit_usdc:.4f} = ${balance.available_balance:.2f}")
    check("Close exit_usdc > 0", exit_usdc > 0, f"${exit_usdc:.4f}")
    check("No claims created (token satildi)", len(claim_mgr.get_claims_by_position(pos.position_id)) == 0)


async def main():
    print(f"\n{HDR}{'#' * 60}")
    print(f"  FAZ 6 INTEGRATION E2E")
    print(f"  Paper Mode -- Tum Akis Halkalari")
    print(f"{'#' * 60}{RST}")

    await test_full_tp_cycle()
    await test_full_sl_cycle()
    await test_full_force_sell_cycle()
    await test_full_manual_close_cycle()
    await test_pending_trade_block()
    await test_external_reconciliation()
    await test_idempotent_settlement()
    await test_balance_consistency()

    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    failed = total - passed

    print(f"\n{HDR}{'=' * 60}")
    print(f"  SONUC: {passed}/{total} passed", end="")
    if failed:
        print(f", {failed} FAILED")
    else:
        print(f" -- ALL GREEN")
    print(f"{'=' * 60}{RST}")

    if failed:
        print(f"\n{FAIL} Basarisiz:")
        for label, ok in results:
            if not ok:
                print(f"  - {label}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
