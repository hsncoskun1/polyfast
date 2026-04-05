"""v0.4.5 CANLI EVALUATION E2E — gerçek Polymarket verisiyle uçtan uca test.

Bu trading e2e DEĞİL — sadece sinyal üretimi doğrulanır.
Order gönderme YOK.

Zincir:
1. Discovery → aktif event bul
2. CoinSettings → test ayarları oluştur
3. CoinPriceClient → coin USD fiyat çek
4. PTB → event PTB çek
5. CLOB WS → outcome fiyat çek (RTDSClient + WSPriceBridge)
6. EvaluationLoop → context doldur → RuleEngine evaluate
7. ENTRY / NO_ENTRY / WAITING sinyali üret

6 coin ile gerçek Polymarket verisi kullanılır.
"""

import asyncio
import json
import re
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.market_data.live_price import LivePricePipeline
from backend.market_data.rtds_client import RTDSClient
from backend.market_data.ws_price_bridge import WSPriceBridge
from backend.market_data.coin_price_client import CoinPriceClient
from backend.ptb.ssr_adapter import SSRPTBAdapter
from backend.ptb.fetcher import PTBFetcher
from backend.settings.settings_store import SettingsStore
from backend.settings.coin_settings import CoinSettings, SideMode
from backend.strategy.engine import RuleEngine
from backend.strategy.rule_state import OverallDecision
from backend.orchestrator.evaluation_loop import EvaluationLoop

ASSETS = ["BTC", "ETH", "SOL", "DOGE", "XRP", "BNB"]
SLOT_SECONDS = 300


async def run_e2e():
    print("=" * 70)
    print("v0.4.5 CANLI EVALUATION E2E")
    print("Trading e2e DEĞİL — sadece sinyal üretimi")
    print("=" * 70)
    print()

    now = int(time.time())
    slot = (now // SLOT_SECONDS) * SLOT_SECONDS
    elapsed = now - slot
    remaining = SLOT_SECONDS - elapsed

    if elapsed < 30:
        wait = 30 - elapsed
        print(f"PTB için {wait}s bekleniyor...")
        await asyncio.sleep(wait)
        now = int(time.time())
        slot = (now // SLOT_SECONDS) * SLOT_SECONDS

    print(f"Slot: {slot}, Elapsed: {now - slot}s, Remaining: {slot + 300 - now}s")
    print()

    # ═══ 1. DISCOVERY ═══
    print("[1] DISCOVERY — aktif event'leri bul")
    token_map = {}  # asset → {condition_id, token_ids, sides}
    async with httpx.AsyncClient(timeout=10) as client:
        for asset in ASSETS:
            slug = f"{asset.lower()}-updown-5m-{slot}"
            r = await client.get("https://gamma-api.polymarket.com/markets", params={"slug": slug})
            markets = r.json()
            if markets:
                m = markets[0]
                cond_id = m.get("conditionId", "")
                clob_ids = json.loads(m.get("clobTokenIds", "[]"))
                outcomes = json.loads(m.get("outcomes", "[]"))
                sides = []
                for i, o in enumerate(outcomes):
                    sides.append("up" if o.lower() in ("up", "yes") else "down")
                token_map[asset] = {
                    "condition_id": cond_id,
                    "token_ids": clob_ids,
                    "sides": sides,
                    "slug": slug,
                }
                print(f"  {asset}: {slug} ({len(clob_ids)} tokens)")

    found = len(token_map)
    print(f"  Bulunan: {found}/{len(ASSETS)}")
    print()

    # ═══ 2. COIN SETTINGS ═══
    print("[2] COIN SETTINGS — test ayarları")
    store = SettingsStore()
    for asset in ASSETS:
        if asset in token_map:
            store.set(CoinSettings(
                coin=asset, coin_enabled=True,
                side_mode=SideMode.DOMINANT_ONLY,
                delta_threshold=0.01,  # çok düşük — hemen sağlansın
                price_min=51, price_max=99,
                spread_max=50.0,  # çok yüksek — hemen sağlansın
                time_min=1, time_max=299,
                event_max=1, order_amount=5.0,
            ))
    print(f"  Eligible: {store.eligible_count}/{len(ASSETS)}")
    print()

    # ═══ 3. COIN USD FİYAT ═══
    print("[3] COIN USD — batch poll")
    coin_client = CoinPriceClient()
    coin_client.set_coins(list(token_map.keys()))
    t0 = time.time()
    prices = await coin_client.poll_once()
    poll_ms = (time.time() - t0) * 1000
    for asset, price in sorted(prices.items()):
        print(f"  {asset}: ${price:,.4f}")
    print(f"  Poll: {poll_ms:.0f}ms, {len(prices)}/{len(token_map)} coin")
    print()

    # ═══ 4. PTB ═══
    print("[4] PTB — event açılış fiyatı")
    ssr = SSRPTBAdapter()
    ptb_fetcher = PTBFetcher(source=ssr)
    for asset, info in token_map.items():
        record = await ptb_fetcher.fetch_ptb(info["condition_id"], asset, info["slug"])
        if record.is_locked:
            print(f"  {asset}: PTB=${record.ptb_value:,.4f} OK")
        else:
            print(f"  {asset}: PTB=YOK ({record.status.value})")
    print()

    # ═══ 5. CLOB WS — outcome fiyat ═══
    print("[5] CLOB WS — outcome fiyat (gerçek WS)")
    pipeline = LivePricePipeline()
    bridge = WSPriceBridge(pipeline)

    # Token route kaydet
    all_token_ids = []
    for asset, info in token_map.items():
        for i, tid in enumerate(info["token_ids"]):
            side = info["sides"][i] if i < len(info["sides"]) else "up"
            bridge.register_token(tid, info["condition_id"], asset, side)
            all_token_ids.append(tid)

    # CLOB WS bağlan + subscribe
    rtds = RTDSClient(on_message=bridge.on_ws_message)
    connected = await rtds.connect()
    if connected:
        await rtds.subscribe(all_token_ids)
        recv_task = rtds.start_receive_loop()
        await asyncio.sleep(3)  # veri toplanması için bekle
        await rtds.disconnect()

    records = pipeline.get_all_records()
    for r in records:
        print(f"  {r.asset}: UP={r.up_price:.4f} DOWN={r.down_price:.4f} spread={r.spread:.4f} source={r.source}")
    print(f"  {len(records)} event outcome verisi alındı")
    print()

    # ═══ 6. EVALUATION ═══
    print("[6] EVALUATION — rule engine")
    engine = RuleEngine()
    eval_loop = EvaluationLoop(engine, pipeline, coin_client, ptb_fetcher, store)

    results = {}
    eligible = store.get_eligible_coins()
    for settings in eligible:
        result = eval_loop._evaluate_single(settings)
        if result:
            results[settings.coin] = result
            decision = result.decision.value
            detail_parts = []
            for rr in result.rule_results:
                detail_parts.append(f"{rr.rule_name}={rr.state.value}")
            rules_str = ", ".join(detail_parts)
            symbol = "OK" if result.decision == OverallDecision.ENTRY else "WAIT" if result.decision == OverallDecision.WAITING else "NO"
            print(f"  {settings.coin}: {symbol} {decision} [{rules_str}]")

    print()

    # ═══ SONUÇ ═══
    print("=" * 70)
    print("CANLI EVALUATION E2E SONUC")
    print("=" * 70)

    checks = [
        ("Discovery", found >= 4),
        ("Coin USD fiyat", len(prices) >= 4),
        ("PTB acquired", ptb_fetcher.locked_count >= 4),
        ("CLOB WS outcome", len(records) >= 4),
        ("Evaluation çalıştı", len(results) >= 4),
        ("Sinyal üretildi", all(r.decision in (OverallDecision.ENTRY, OverallDecision.NO_ENTRY, OverallDecision.WAITING) for r in results.values())),
    ]

    all_pass = True
    for name, ok in checks:
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  [{status}] {name}")

    print()
    entry_count = sum(1 for r in results.values() if r.decision == OverallDecision.ENTRY)
    waiting_count = sum(1 for r in results.values() if r.decision == OverallDecision.WAITING)
    no_entry_count = sum(1 for r in results.values() if r.decision == OverallDecision.NO_ENTRY)
    print(f"  ENTRY: {entry_count}, NO_ENTRY: {no_entry_count}, WAITING: {waiting_count}")
    print(f"  Toplam evaluation: {len(results)}/{len(ASSETS)}")
    print()

    if all_pass:
        print("SONUC: TUM KONTROLLER GECTI — Faz 4 canli evaluation e2e BASARILI")
    else:
        print("SONUC: BAZI KONTROLLER BASARISIZ")


if __name__ == "__main__":
    asyncio.run(run_e2e())
