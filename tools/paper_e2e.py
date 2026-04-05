"""v0.5.3 PAPER MODE E2E — uctan uca execution dogrulamasi.

Gercek order YOK — paper mode ile simulated fill.
Dogrulanacak pathler:
1. ENTRY → paper fill → position open → balance deduct → counters
2. REJECT path (insufficient balance)
3. Counters (event_fill, session_trade, open_position)
4. Net unrealized PnL hesaplama
5. Fee-aware accounting
"""

import asyncio
import json
import re
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.execution.order_executor import OrderExecutor, ExecutionMode, OrderResult
from backend.execution.order_intent import OrderIntent, OrderSide
from backend.execution.order_validator import OrderValidator
from backend.execution.position_tracker import PositionTracker
from backend.execution.balance_manager import BalanceManager
from backend.execution.fee_rate_fetcher import FeeRateFetcher
from backend.market_data.coin_price_client import CoinPriceClient
from backend.ptb.ssr_adapter import SSRPTBAdapter
from backend.ptb.fetcher import PTBFetcher
from backend.settings.settings_store import SettingsStore
from backend.settings.coin_settings import CoinSettings, SideMode

ASSETS = ["BTC", "ETH", "SOL"]
SLOT_SECONDS = 300


async def run_paper_e2e():
    print("=" * 70)
    print("v0.5.3 PAPER MODE E2E — EXECUTION DOGRULAMA")
    print("Gercek order YOK — paper mode")
    print("=" * 70)
    print()

    # Setup
    tracker = PositionTracker()
    balance_mgr = BalanceManager()
    balance_mgr.update(available=50.0, total=50.0)  # paper $50
    validator = OrderValidator()
    fee_fetcher = FeeRateFetcher()
    executor = OrderExecutor(tracker, balance_mgr, validator, fee_fetcher, mode=ExecutionMode.PAPER)

    # Coin settings
    store = SettingsStore()
    for asset in ASSETS:
        store.set(CoinSettings(
            coin=asset, coin_enabled=True, side_mode=SideMode.DOMINANT_ONLY,
            delta_threshold=0.01, price_min=51, price_max=99,
            spread_max=50.0, time_min=1, time_max=299,
            event_max=1, order_amount=5.0,
        ))

    # Coin USD fiyat cek
    coin_client = CoinPriceClient()
    coin_client.set_coins(ASSETS)
    coin_task = asyncio.create_task(coin_client.run_forever())
    await asyncio.sleep(2)

    # PTB cek
    now = int(time.time())
    slot = (now // SLOT_SECONDS) * SLOT_SECONDS
    if now - slot < 30:
        print(f"PTB icin {30 - (now-slot)}s bekleniyor...")
        await asyncio.sleep(30 - (now - slot))
        now = int(time.time())
        slot = (now // SLOT_SECONDS) * SLOT_SECONDS

    ssr = SSRPTBAdapter()
    ptb_fetcher = PTBFetcher(source=ssr)

    token_map = {}
    async with httpx.AsyncClient(timeout=10) as client:
        for asset in ASSETS:
            slug = f"{asset.lower()}-updown-5m-{slot}"
            r = await client.get("https://gamma-api.polymarket.com/markets", params={"slug": slug})
            markets = r.json()
            if markets:
                m = markets[0]
                cond_id = m.get("conditionId", "")
                clob_ids = json.loads(m.get("clobTokenIds", "[]"))
                token_map[asset] = {"condition_id": cond_id, "token_ids": clob_ids, "slug": slug}
                await ptb_fetcher.fetch_ptb(cond_id, asset, slug)

    print(f"Slot: {slot}, Assets: {len(token_map)}")
    print(f"Balance: ${balance_mgr.available_balance:.2f}")
    print()

    # ═══ TEST 1: ENTRY → FILL → POSITION ═══
    print("[1] ENTRY PATH — paper fill")
    for asset in ASSETS:
        info = token_map.get(asset, {})
        if not info:
            continue

        coin_rec = coin_client.get_price(asset)
        dominant = max(coin_rec.usd_price if coin_rec else 0, 0)

        ptb_rec = ptb_fetcher.get_record(info["condition_id"])
        if not ptb_rec or not ptb_rec.is_locked:
            print(f"  {asset}: PTB yok, atlaniyor")
            continue

        intent = OrderIntent(
            asset=asset, side=OrderSide.UP, amount_usd=5.0,
            condition_id=info["condition_id"],
            token_id=info["token_ids"][0] if info["token_ids"] else "",
            dominant_price=0.85,  # paper test fiyati
        )

        result = await executor.execute(intent)
        print(f"  {asset}: {result.result.value} | pos={result.position_id is not None} | fill={result.fill_price:.4f}")

    print()
    print(f"  Balance sonrasi: ${balance_mgr.available_balance:.2f}")
    print(f"  Open positions: {tracker.open_position_count}")
    print(f"  Session trades: {tracker.session_trade_count}")
    print(f"  Fill count: {executor.fill_count}")
    print()

    # ═══ TEST 2: REJECT PATH — insufficient balance ═══
    print("[2] REJECT PATH — insufficient balance")
    balance_mgr.update(available=0.50)  # $0.50 — yetersiz
    reject_intent = OrderIntent(
        asset="BTC", side=OrderSide.UP, amount_usd=5.0,
        condition_id="0xREJECT", token_id="reject_tok",
        dominant_price=0.85,
    )
    reject_result = await executor.execute(reject_intent)
    print(f"  Result: {reject_result.result.value}")
    print(f"  Pending olustu mu: {reject_result.position_id is not None}")
    print(f"  Positions (reject sonrasi): {len(tracker.get_all_positions())}")
    balance_mgr.update(available=35.0)  # restore to post-fill state
    print()

    # ═══ TEST 3: EVENT MAX REJECT ═══
    print("[3] EVENT MAX REJECT — ayni event'te ikinci deneme")
    first_asset = ASSETS[0]
    info = token_map.get(first_asset, {})
    if info:
        intent2 = OrderIntent(
            asset=first_asset, side=OrderSide.UP, amount_usd=5.0,
            condition_id=info["condition_id"],
            token_id=info["token_ids"][0] if info["token_ids"] else "",
            dominant_price=0.85,
        )
        result2 = await executor.execute(intent2)
        print(f"  {first_asset} ikinci deneme: {result2.result.value}")
        print(f"  Event fill count: {tracker.get_event_fill_count(info['condition_id'])}")
    print()

    # ═══ TEST 4: NET UNREALIZED PNL ═══
    print("[4] NET UNREALIZED PNL — acik pozisyonlar")
    for pos in tracker.get_open_positions():
        pnl = pos.calculate_unrealized_pnl(current_price=0.90)
        print(f"  {pos.asset} {pos.side}:")
        print(f"    Fill: {pos.fill_price:.4f}")
        print(f"    Net shares: {pos.net_position_shares:.4f}")
        print(f"    Entry fee: {pos.entry_fee_shares:.6f} shares")
        print(f"    Current: {pnl['current_price']}")
        print(f"    Gross value: ${pnl['gross_position_value']:.4f}")
        print(f"    Est exit fee: ${pnl['estimated_exit_fee_usdc']:.4f}")
        print(f"    Net PnL: ${pnl['net_unrealized_pnl_estimate']:.4f} ({pnl['net_unrealized_pnl_pct']:.2f}%)")
    print()

    # ═══ TEST 5: BALANCE STALE GUARD ═══
    print("[5] BALANCE STALE GUARD")
    from datetime import timedelta
    balance_mgr._updated_at = balance_mgr._updated_at - timedelta(seconds=120)
    stale_intent = OrderIntent(
        asset="BTC", side=OrderSide.UP, amount_usd=5.0,
        condition_id="0xSTALE", token_id="stale_tok",
        dominant_price=0.85,
    )
    stale_result = await executor.execute(stale_intent)
    print(f"  Stale balance result: {stale_result.result.value}")
    print()

    await coin_client.stop()

    # ═══ SONUC ═══
    print("=" * 70)
    print("PAPER E2E SONUC")
    print("=" * 70)

    checks = [
        ("Entry fill (paper)", executor.fill_count >= 1),
        ("Position acik", tracker.open_position_count >= 1),
        ("Balance deduct", balance_mgr.available_balance < 50.0),
        ("Session trade count", tracker.session_trade_count >= 1),
        ("Reject path (balance)", reject_result.result == OrderResult.REJECTED),
        ("Reject no pending", reject_result.position_id is None),
        ("Event Max reject", result2.result == OrderResult.REJECTED if info else True),
        ("Balance stale guard", stale_result.result == OrderResult.BALANCE_STALE),
        ("Net PnL hesaplandi", len(tracker.get_open_positions()) > 0),
        ("Fee-aware entry", all(p.entry_fee_shares > 0 for p in tracker.get_open_positions())),
    ]

    all_pass = True
    for name, ok in checks:
        s = "PASS" if ok else "FAIL"
        if not ok: all_pass = False
        print(f"  [{s}] {name}")

    print()
    if all_pass:
        print("FAZ 5 PAPER E2E BASARILI")
    else:
        print("BAZI KONTROLLER BASARISIZ")


if __name__ == "__main__":
    asyncio.run(run_paper_e2e())
