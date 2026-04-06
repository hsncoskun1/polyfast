"""v0.6.5 PAPER EXIT E2E — uctan uca exit + settlement dogrulamasi.

Gercek order YOK — paper mode ile simulated fill.
Dogrulanacak pathler:
1. ENTRY -> TP close -> settlement (kazanan) -> balance artar
2. ENTRY -> SL close -> settlement (kaybeden) -> balance degismez
3. ENTRY -> Force Sell close -> settlement
4. ENTRY -> Manual Close -> settlement
5. Settlement: zaten settled pozisyon skip edilir
6. Settlement: acik pozisyon skip edilir
7. Relayer guard: LIVE_SETTLEMENT_ENABLED=False -> gercek TX cikmaz

Calistirma:
    python tools/paper_exit_e2e.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.execution.order_executor import OrderExecutor, ExecutionMode
from backend.execution.order_intent import OrderIntent, OrderSide
from backend.execution.order_validator import OrderValidator
from backend.execution.position_tracker import PositionTracker
from backend.execution.balance_manager import BalanceManager
from backend.execution.fee_rate_fetcher import FeeRateFetcher
from backend.execution.exit_evaluator import ExitEvaluator
from backend.execution.exit_executor import ExitExecutor
from backend.execution.claim_manager import ClaimManager, ClaimOutcome
from backend.execution.close_reason import CloseReason, ForceSellTrigger
from backend.execution.position_record import PositionState
from backend.execution.relayer_client_wrapper import RelayerClientWrapper, LIVE_SETTLEMENT_ENABLED
from backend.orchestrator.settlement import SettlementOrchestrator

PASS = "\033[92mOK\033[0m"
FAIL = "\033[91mFAIL\033[0m"
HDR = "\033[96m"
RST = "\033[0m"

results = []


def check(label: str, condition: bool, detail: str = ""):
    tag = PASS if condition else FAIL
    extra = f"  ({detail})" if detail else ""
    print(f"  {tag} {label}{extra}")
    results.append((label, condition))


def header(title: str):
    print(f"\n{HDR}{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}{RST}")


def _setup():
    """Ortak test objelerini olustur."""
    tracker = PositionTracker()
    balance = BalanceManager()
    balance.update(available=100.0)
    claim_mgr = ClaimManager(balance, paper_mode=True)
    relayer = RelayerClientWrapper()
    settlement = SettlementOrchestrator(tracker, claim_mgr, relayer, paper_mode=True)
    exit_eval = ExitEvaluator(tp_reevaluate=True)
    exit_exec = ExitExecutor(tracker, balance, paper_mode=True)
    return tracker, balance, claim_mgr, relayer, settlement, exit_eval, exit_exec


async def _open_position(tracker, balance, asset="BTC", fill_price=0.85, amount=5.0):
    """Pozisyon ac ve fill et."""
    pos = tracker.create_pending(asset, "UP", "0x1", "tok1", amount)
    tracker.confirm_fill(pos.position_id, fill_price=fill_price)
    return pos


async def test_tp_close_settlement():
    """PATH 1: Entry -> TP close -> settlement (kazanan) -> balance artar."""
    header("PATH 1: TP CLOSE -> SETTLEMENT (KAZANAN)")
    tracker, balance, claim_mgr, relayer, settlement, exit_eval, exit_exec = _setup()

    # Entry
    pos = await _open_position(tracker, balance, fill_price=0.85)
    check("Position opened", pos.is_open, f"state={pos.state.value}")
    initial_balance = balance.available_balance

    # TP evaluation — current price yuksek
    current_price = 0.92
    tp_pct = 5.0  # %5 TP
    net_pnl_pct = (current_price - pos.fill_price) / pos.fill_price * 100
    check("Net PnL > TP threshold", net_pnl_pct >= tp_pct, f"pnl={net_pnl_pct:.2f}%, tp={tp_pct}%")

    # Close request
    tracker.request_close(pos.position_id, CloseReason.TAKE_PROFIT)
    check("Close requested", pos.state.value == "closing_requested")

    # Execute close
    success = await exit_exec.execute_close(pos, current_price=current_price)
    check("Close executed", success is True)
    check("Position closed", pos.is_closed)
    check("Net realized PnL > 0", pos.net_realized_pnl > 0, f"pnl=${pos.net_realized_pnl:.4f}")

    # Settlement
    settled = await settlement.process_settlements()
    check("Settlement processed", settled == 1)

    claims = claim_mgr.get_claims_by_position(pos.position_id)
    check("Claim created", len(claims) == 1)
    check("Claim outcome: REDEEMED_WON", claims[0].outcome == ClaimOutcome.REDEEMED_WON)
    check("Claimed amount > 0", claims[0].claimed_amount_usdc > 0, f"${claims[0].claimed_amount_usdc:.4f}")
    check("Balance increased", balance.available_balance > initial_balance,
          f"${initial_balance:.2f} -> ${balance.available_balance:.2f}")


async def test_sl_close_settlement():
    """PATH 2: Entry -> SL close -> settlement (kaybeden) -> balance degismez."""
    header("PATH 2: SL CLOSE -> SETTLEMENT (KAYBEDEN)")
    tracker, balance, claim_mgr, relayer, settlement, exit_eval, exit_exec = _setup()

    # Entry
    pos = await _open_position(tracker, balance, fill_price=0.85)
    check("Position opened", pos.is_open)

    # SL evaluation — current price dusuk
    current_price = 0.78
    net_pnl_pct = (current_price - pos.fill_price) / pos.fill_price * 100
    check("Net PnL < 0 (loss)", net_pnl_pct < 0, f"pnl={net_pnl_pct:.2f}%")

    # Close request — SL latch
    tracker.request_close(pos.position_id, CloseReason.STOP_LOSS)
    check("SL close requested", pos.state.value == "closing_requested")
    check("Close reason: STOP_LOSS", pos.close_reason == CloseReason.STOP_LOSS)

    # SL latch: should_cancel_close always False
    cancel = exit_eval.should_cancel_close(pos, current_price=0.95)
    check("SL latch: cancel=False (even if price recovered)", cancel is False)

    # Execute close
    success = await exit_exec.execute_close(pos, current_price=current_price)
    check("Close executed", success is True)
    check("Position closed", pos.is_closed)
    check("Net realized PnL < 0", pos.net_realized_pnl < 0, f"pnl=${pos.net_realized_pnl:.4f}")

    # Settlement
    before_balance = balance.available_balance
    settled = await settlement.process_settlements()
    check("Settlement processed", settled == 1)

    claims = claim_mgr.get_claims_by_position(pos.position_id)
    check("Claim outcome: REDEEMED_LOST", claims[0].outcome == ClaimOutcome.REDEEMED_LOST)
    check("Claimed amount = $0", claims[0].claimed_amount_usdc == 0.0)
    check("Balance unchanged", balance.available_balance == before_balance,
          f"${before_balance:.2f} -> ${balance.available_balance:.2f}")


async def test_force_sell_close_settlement():
    """PATH 3: Entry -> Force Sell close -> settlement."""
    header("PATH 3: FORCE SELL CLOSE -> SETTLEMENT")
    tracker, balance, claim_mgr, relayer, settlement, exit_eval, exit_exec = _setup()

    pos = await _open_position(tracker, balance, fill_price=0.85)
    check("Position opened", pos.is_open)

    # Force sell — latch (no cancel)
    tracker.request_close(
        pos.position_id, CloseReason.FORCE_SELL,
        trigger_set=[ForceSellTrigger.TIME, ForceSellTrigger.PNL],
    )
    check("Force sell requested", pos.state.value == "closing_requested")
    check("Close reason: FORCE_SELL", pos.close_reason == CloseReason.FORCE_SELL)
    check("Trigger set: time+pnl", len(pos.close_trigger_set) == 2)

    # Force sell latch
    cancel = exit_eval.should_cancel_close(pos, current_price=0.95)
    check("Force sell latch: cancel=False", cancel is False)

    # Execute — slight loss
    success = await exit_exec.execute_close(pos, current_price=0.82)
    check("Close executed", success is True)
    check("Position closed", pos.is_closed)

    # Settlement
    settled = await settlement.process_settlements()
    check("Settlement processed", settled == 1)
    claims = claim_mgr.get_claims_by_position(pos.position_id)
    check("Claim created", len(claims) == 1)


async def test_manual_close_settlement():
    """PATH 4: Entry -> Manual Close -> settlement."""
    header("PATH 4: MANUAL CLOSE -> SETTLEMENT")
    tracker, balance, claim_mgr, relayer, settlement, exit_eval, exit_exec = _setup()

    pos = await _open_position(tracker, balance, fill_price=0.85)
    check("Position opened", pos.is_open)

    # Manual close — latch
    tracker.request_close(pos.position_id, CloseReason.MANUAL_CLOSE)
    check("Manual close requested", pos.state.value == "closing_requested")
    check("Close reason: MANUAL_CLOSE", pos.close_reason == CloseReason.MANUAL_CLOSE)
    check("No trigger set (user initiated)", pos.close_trigger_set == [])

    # Manual close latch
    cancel = exit_eval.should_cancel_close(pos, current_price=0.95)
    check("Manual latch: cancel=False", cancel is False)

    # Execute — small profit
    success = await exit_exec.execute_close(pos, current_price=0.88)
    check("Close executed", success is True)
    check("Position closed", pos.is_closed)

    # Settlement
    settled = await settlement.process_settlements()
    check("Settlement processed", settled == 1)
    claims = claim_mgr.get_claims_by_position(pos.position_id)
    check("Claim created", len(claims) == 1)


async def test_already_settled_skipped():
    """PATH 5: Zaten settled pozisyon skip edilir."""
    header("PATH 5: ALREADY SETTLED -> SKIP")
    tracker, balance, claim_mgr, relayer, settlement, exit_eval, exit_exec = _setup()

    pos = await _open_position(tracker, balance, fill_price=0.85)
    tracker.request_close(pos.position_id, CloseReason.TAKE_PROFIT)
    await exit_exec.execute_close(pos, current_price=0.92)

    # First settlement
    settled1 = await settlement.process_settlements()
    check("First settlement: 1", settled1 == 1)

    # Second — already settled
    settled2 = await settlement.process_settlements()
    check("Second settlement: 0 (skipped)", settled2 == 0)


async def test_open_position_not_settled():
    """PATH 6: Acik pozisyon settle edilmez."""
    header("PATH 6: OPEN POSITION -> NOT SETTLED")
    tracker, balance, claim_mgr, relayer, settlement, exit_eval, exit_exec = _setup()

    pos = await _open_position(tracker, balance, fill_price=0.85)
    check("Position is open", pos.is_open)

    settled = await settlement.process_settlements()
    check("Settlement: 0 (open not settled)", settled == 0)


async def test_relayer_guard():
    """PATH 7: LIVE_SETTLEMENT_ENABLED=False -> gercek TX cikmaz."""
    header("PATH 7: RELAYER GUARD")
    check("LIVE_SETTLEMENT_ENABLED is False", LIVE_SETTLEMENT_ENABLED is False)

    relayer = RelayerClientWrapper()
    result = await relayer.redeem_positions("0x1", "UP")
    check("Redeem blocked", result["success"] is False)
    check("Guard flag present", result.get("guard") is True)

    # With credentials — still blocked
    relayer2 = RelayerClientWrapper(
        private_key="0xabc", relayer_api_key="key", relayer_address="0x123",
    )
    check("Initialized with creds", relayer2.is_initialized is True)
    result2 = await relayer2.redeem_positions("0x1", "UP")
    check("Still blocked by guard", result2["success"] is False)


async def test_tp_reevaluate():
    """BONUS: TP reevaluate — fiyat geri cekildiyse close iptal edilir."""
    header("BONUS: TP REEVALUATE")
    tracker, balance, claim_mgr, relayer, settlement, exit_eval, exit_exec = _setup()

    pos = await _open_position(tracker, balance, fill_price=0.85)
    tracker.request_close(pos.position_id, CloseReason.TAKE_PROFIT)
    check("TP close requested", pos.state.value == "closing_requested")

    # Price pulled back — TP no longer met
    cancel = exit_eval.should_cancel_close(pos, current_price=0.86)
    check("TP reevaluate: cancel=True (price dropped)", cancel is True)

    # Revert to open (TP reevaluate cancels close)
    pos.transition_to(PositionState.OPEN_CONFIRMED)
    check("Position back to open", pos.is_open)


async def main():
    print(f"\n{HDR}{'#' * 60}")
    print(f"  PAPER EXIT E2E — v0.6.5 Settlement Full Cycle")
    print(f"{'#' * 60}{RST}")

    await test_tp_close_settlement()
    await test_sl_close_settlement()
    await test_force_sell_close_settlement()
    await test_manual_close_settlement()
    await test_already_settled_skipped()
    await test_open_position_not_settled()
    await test_relayer_guard()
    await test_tp_reevaluate()

    # Summary
    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    failed = total - passed

    print(f"\n{HDR}{'=' * 60}")
    print(f"  SONUC: {passed}/{total} passed", end="")
    if failed:
        print(f", {failed} FAILED")
    else:
        print(f" — ALL GREEN")
    print(f"{'=' * 60}{RST}")

    if failed:
        print(f"\n{FAIL} Basarisiz testler:")
        for label, ok in results:
            if not ok:
                print(f"  - {label}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
