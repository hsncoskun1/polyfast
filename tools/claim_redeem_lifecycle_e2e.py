"""CLAIM / REDEEM CANLI-AKIS DOGRULAMA — Paper/Test Mode E2E

Gercek para/live TX YOK — paper mode'da gercek orchestration akisini dogrular.

10 dogrulama maddesi:
1) Closed position settlement adayina donusuyor mu
2) Resolved/redeemable kontrolu akisa dogru giriyor mu
3) ClaimRecord / settlement record dogru olusuyor mu
4) Retry lifecycle gercekten calisiyor mu
5) Pending settlement varken new trade block gercekten calisiyor mu
6) payout > 0 ise won settlement
7) payout = 0 ise lost settlement
8) Post-claim/redeem balance refresh akisa giriyor mu
9) Ikinci kez settle etmeye calisinca skip/idempotent davraniyor mu
10) Manual close, TP, SL, force sell kapanislarindan sonra settlement akisi tutarli mi

Calistirma:
    python tools/claim_redeem_lifecycle_e2e.py
"""

import asyncio
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.execution.position_tracker import PositionTracker
from backend.execution.balance_manager import BalanceManager
from backend.execution.claim_manager import ClaimManager, ClaimOutcome, ClaimStatus
from backend.execution.close_reason import CloseReason, ForceSellTrigger
from backend.execution.position_record import PositionState
from backend.execution.order_validator import OrderValidator
from backend.execution.order_intent import OrderIntent, OrderSide
from backend.execution.models import ValidationStatus, RejectReason
from backend.execution.relayer_client_wrapper import RelayerClientWrapper
from backend.orchestrator.settlement import SettlementOrchestrator
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


class MockPTBFetcher:
    def __init__(self):
        self._records = {}

    def set_ptb(self, condition_id, asset, value):
        rec = PTBRecord(condition_id=condition_id, asset=asset)
        rec.lock(value, "test_mock")
        self._records[condition_id] = rec

    def get_record(self, condition_id):
        return self._records.get(condition_id)


class MockCoinPriceClient:
    def __init__(self):
        self._prices = {}

    def set_price(self, coin, usd_price):
        self._prices[coin] = usd_price

    def get_usd_price(self, coin):
        return self._prices.get(coin, 0.0)


def _setup(ptb_value=67000.0, coin_usd=67500.0):
    tracker = PositionTracker()
    balance = BalanceManager()
    balance.update(available=100.0)
    claim_mgr = ClaimManager(balance, paper_mode=True)
    relayer = RelayerClientWrapper()

    ptb = MockPTBFetcher()
    ptb.set_ptb("0x1", "BTC", ptb_value)

    coin = MockCoinPriceClient()
    coin.set_price("BTC", coin_usd)

    orch = SettlementOrchestrator(
        tracker, claim_mgr, relayer, paper_mode=True,
        ptb_fetcher=ptb, coin_price_client=coin,
    )
    return tracker, balance, claim_mgr, orch


def _open_and_close(tracker, reason, fill=0.85, exit_price=0.92, triggers=None):
    pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 5.0)
    tracker.confirm_fill(pos.position_id, fill_price=fill)
    if triggers:
        tracker.request_close(pos.position_id, reason, trigger_set=triggers)
    else:
        tracker.request_close(pos.position_id, reason)
    tracker.confirm_close(pos.position_id, exit_fill_price=exit_price)
    return pos


# ================================================================
# 1) Closed position settlement adayina donusuyor mu
# ================================================================
async def test_1_closed_becomes_settlement_candidate():
    header("1) CLOSED POSITION -> SETTLEMENT ADAYI")
    tracker, balance, claim_mgr, orch = _setup()

    pos = _open_and_close(tracker, CloseReason.TAKE_PROFIT)
    check("Position is closed", pos.is_closed)
    check("closed_at is set", pos.closed_at is not None)

    settled = await orch.process_settlements()
    check("Settlement processed (1 settled)", settled == 1)

    claims = claim_mgr.get_claims_by_position(pos.position_id)
    check("ClaimRecord created for closed position", len(claims) == 1)


# ================================================================
# 2) Resolved/redeemable kontrolu akisa dogru giriyor mu
# ================================================================
async def test_2_resolved_redeemable_check():
    header("2) RESOLVED / REDEEMABLE KONTROLU")
    tracker, balance, claim_mgr, orch = _setup()

    # Paper mode'da _check_resolved() True doner (paper placeholder)
    is_resolved = await orch._check_resolved("0x1")
    check("Paper mode: resolved=True (placeholder)", is_resolved is True)

    # Acik pozisyon settle edilmez (resolved kontrolune bile girmez)
    pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 5.0)
    tracker.confirm_fill(pos.position_id, fill_price=0.85)
    settled = await orch.process_settlements()
    check("Open position not settled", settled == 0)


# ================================================================
# 3) ClaimRecord / settlement record dogru olusuyor mu
# ================================================================
async def test_3_claim_record_creation():
    header("3) CLAIM RECORD OLUSUMU")
    tracker, balance, claim_mgr, orch = _setup(coin_usd=67500.0)  # UP kazanir

    pos = _open_and_close(tracker, CloseReason.TAKE_PROFIT)
    await orch.process_settlements()

    claims = claim_mgr.get_claims_by_position(pos.position_id)
    c = claims[0]
    check("claim_id is set", bool(c.claim_id))
    check("condition_id matches", c.condition_id == "0x1")
    check("position_id matches", c.position_id == pos.position_id)
    check("asset matches", c.asset == "BTC")
    check("side matches", c.side == "UP")
    check("claim_status = SUCCESS", c.claim_status == ClaimStatus.SUCCESS)
    check("claimed_at is set", c.claimed_at is not None)
    check("outcome = REDEEMED_WON", c.outcome == ClaimOutcome.REDEEMED_WON)
    check("claimed_amount > 0", c.claimed_amount_usdc > 0)


# ================================================================
# 4) Retry lifecycle gercekten calisiyor mu
# ================================================================
async def test_4_retry_lifecycle():
    header("4) RETRY LIFECYCLE")
    tracker = PositionTracker()
    balance = BalanceManager()
    balance.update(available=100.0)
    claim_mgr = ClaimManager(balance, paper_mode=False)  # live mode -> fail
    relayer = RelayerClientWrapper()
    orch = SettlementOrchestrator(tracker, claim_mgr, relayer, paper_mode=False)

    pos = _open_and_close(tracker, CloseReason.TAKE_PROFIT)

    # 1. Ilk settlement basarisiz (live guard)
    settled = await orch.process_settlements()
    check("First attempt: settled=0 (live guard)", settled == 0)
    check("Retry state created", orch.pending_retry_count == 1)

    # 2. Retry zamani henuz gelmedi
    settled2 = await orch.process_settlements()
    check("Not ready yet: settled=0", settled2 == 0)
    check("Still pending", orch.pending_retry_count == 1)

    # 3. Retry zamanini gecmise cek + paper mode
    orch._paper_mode = True
    claim_mgr._paper_mode = True
    for state in orch._retry_states.values():
        state.next_retry_at = time.time() - 1

    settled3 = await orch.process_settlements()
    check("Retry succeeded: settled=1", settled3 == 1)
    check("No more pending retries", orch.pending_retry_count == 0)


# ================================================================
# 5) Pending settlement varken new trade block
# ================================================================
async def test_5_pending_settlement_trade_block():
    header("5) PENDING SETTLEMENT -> TRADE BLOCK")
    tracker = PositionTracker()
    balance = BalanceManager()
    balance.update(available=100.0)
    claim_mgr = ClaimManager(balance, paper_mode=False)
    relayer = RelayerClientWrapper()
    orch = SettlementOrchestrator(tracker, claim_mgr, relayer, paper_mode=False)

    _open_and_close(tracker, CloseReason.TAKE_PROFIT)
    await orch.process_settlements()  # basarisiz -> pending

    check("has_pending_settlements=True", orch.has_pending_settlements() is True)
    check("has_pending_claims=True", claim_mgr.has_pending_claims() is True)

    # OrderValidator ile test
    validator = OrderValidator()
    intent = OrderIntent(
        asset="BTC", side=OrderSide.UP, amount_usd=5.0,
        condition_id="0x2", token_id="tok2", dominant_price=0.55,
    )

    result_blocked = validator.validate(
        intent, available_balance=100.0,
        event_fill_count=0, event_max=5,
        open_position_count=0, bot_max=10,
        has_pending_claims=True, wait_for_claim_redeem=True,
    )
    check("Trade REJECTED (wait=True)", result_blocked.status == ValidationStatus.REJECTED)
    check("Reason: CLAIM_PENDING", result_blocked.reason == RejectReason.CLAIM_PENDING)

    result_allowed = validator.validate(
        intent, available_balance=100.0,
        event_fill_count=0, event_max=5,
        open_position_count=0, bot_max=10,
        has_pending_claims=True, wait_for_claim_redeem=False,
    )
    check("Trade VALID (wait=False)", result_allowed.status == ValidationStatus.VALID)


# ================================================================
# 6) payout > 0 -> won settlement
# ================================================================
async def test_6_payout_positive_won():
    header("6) PAYOUT > 0 -> WON SETTLEMENT")
    tracker, balance, claim_mgr, orch = _setup(ptb_value=67000.0, coin_usd=67500.0)
    # coin_usd > ptb -> UP kazanir

    before = balance.available_balance
    pos = _open_and_close(tracker, CloseReason.TAKE_PROFIT)
    await orch.process_settlements()

    claims = claim_mgr.get_claims_by_position(pos.position_id)
    check("Outcome: REDEEMED_WON", claims[0].outcome == ClaimOutcome.REDEEMED_WON)
    check("Claimed amount > 0", claims[0].claimed_amount_usdc > 0,
          f"${claims[0].claimed_amount_usdc:.4f}")
    check("Resolution method: resolution", orch._last_resolution_method == "resolution")
    check("Balance increased", balance.available_balance > before,
          f"${before:.2f} -> ${balance.available_balance:.2f}")


# ================================================================
# 7) payout = 0 -> lost settlement
# ================================================================
async def test_7_payout_zero_lost():
    header("7) PAYOUT = 0 -> LOST SETTLEMENT")
    tracker, balance, claim_mgr, orch = _setup(ptb_value=67000.0, coin_usd=66500.0)
    # coin_usd < ptb -> DOWN kazanir, UP pozisyon LOST

    pos = _open_and_close(tracker, CloseReason.STOP_LOSS, fill=0.85, exit_price=0.78)
    before = balance.available_balance
    await orch.process_settlements()

    claims = claim_mgr.get_claims_by_position(pos.position_id)
    check("Outcome: REDEEMED_LOST", claims[0].outcome == ClaimOutcome.REDEEMED_LOST)
    check("Claimed amount = $0", claims[0].claimed_amount_usdc == 0.0)
    check("Balance unchanged", balance.available_balance == before,
          f"${before:.2f} -> ${balance.available_balance:.2f}")


# ================================================================
# 8) Post-claim/redeem balance refresh akisa giriyor mu
# ================================================================
async def test_8_post_claim_balance_refresh():
    header("8) POST-CLAIM BALANCE REFRESH")
    tracker, balance, claim_mgr, orch = _setup(coin_usd=67500.0)

    before = balance.available_balance
    pos = _open_and_close(tracker, CloseReason.TAKE_PROFIT)
    await orch.process_settlements()

    claims = claim_mgr.get_claims_by_position(pos.position_id)
    payout = claims[0].claimed_amount_usdc
    check("Payout recorded", payout > 0, f"${payout:.4f}")
    check("Balance = before + payout", abs(balance.available_balance - (before + payout)) < 0.01,
          f"${before:.2f} + ${payout:.4f} = ${balance.available_balance:.2f}")


# ================================================================
# 9) Ikinci kez settle -> skip/idempotent
# ================================================================
async def test_9_idempotent_settlement():
    header("9) IDEMPOTENT SETTLEMENT (SKIP)")
    tracker, balance, claim_mgr, orch = _setup()

    pos = _open_and_close(tracker, CloseReason.TAKE_PROFIT)
    settled1 = await orch.process_settlements()
    check("First settlement: 1", settled1 == 1)

    balance_after_first = balance.available_balance

    settled2 = await orch.process_settlements()
    check("Second settlement: 0 (skipped)", settled2 == 0)
    check("Balance unchanged after skip", balance.available_balance == balance_after_first)

    settled3 = await orch.process_settlements()
    check("Third settlement: 0 (still skipped)", settled3 == 0)

    claims = claim_mgr.get_claims_by_position(pos.position_id)
    check("Still only 1 claim", len(claims) == 1)


# ================================================================
# 10) TP, SL, Force Sell, Manual Close -> settlement tutarliligi
# ================================================================
async def test_10_all_close_reasons_settlement():
    header("10) TUM KAPANIS TURLERI -> SETTLEMENT TUTARLILIGI")

    close_scenarios = [
        ("TP", CloseReason.TAKE_PROFIT, 0.85, 0.92, None, 67500.0),
        ("SL", CloseReason.STOP_LOSS, 0.85, 0.78, None, 66500.0),
        ("FORCE_SELL", CloseReason.FORCE_SELL, 0.85, 0.82,
         [ForceSellTrigger.TIME, ForceSellTrigger.PNL], 66500.0),
        ("MANUAL", CloseReason.MANUAL_CLOSE, 0.85, 0.88, None, 67500.0),
    ]

    for label, reason, fill, exit_p, triggers, coin_usd in close_scenarios:
        tracker, balance, claim_mgr, orch = _setup(coin_usd=coin_usd)
        pos = _open_and_close(tracker, reason, fill=fill, exit_price=exit_p, triggers=triggers)

        settled = await orch.process_settlements()
        claims = claim_mgr.get_claims_by_position(pos.position_id)

        check(f"{label}: settled=1", settled == 1)
        check(f"{label}: claim created", len(claims) == 1)
        check(f"{label}: claim SUCCESS", claims[0].claim_status == ClaimStatus.SUCCESS)

        if coin_usd > 67000.0:  # UP kazanir
            check(f"{label}: WON (UP wins)", claims[0].outcome == ClaimOutcome.REDEEMED_WON)
        else:  # DOWN kazanir
            check(f"{label}: LOST (DOWN wins)", claims[0].outcome == ClaimOutcome.REDEEMED_LOST)


# ================================================================
# MAIN
# ================================================================
async def main():
    print(f"\n{HDR}{'#' * 60}")
    print(f"  CLAIM / REDEEM CANLI-AKIS DOGRULAMA")
    print(f"  Paper/Test Mode E2E — 10 Madde")
    print(f"{'#' * 60}{RST}")

    await test_1_closed_becomes_settlement_candidate()
    await test_2_resolved_redeemable_check()
    await test_3_claim_record_creation()
    await test_4_retry_lifecycle()
    await test_5_pending_settlement_trade_block()
    await test_6_payout_positive_won()
    await test_7_payout_zero_lost()
    await test_8_post_claim_balance_refresh()
    await test_9_idempotent_settlement()
    await test_10_all_close_reasons_settlement()

    # Summary
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
        print(f"\n{FAIL} Basarisiz testler:")
        for label, ok in results:
            if not ok:
                print(f"  - {label}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
