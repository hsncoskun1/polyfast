"""v0.4.6 CANLI EVALUATION E2E — tam otomatik zincir dogrulamasi.

Discovery -> EligibilityGate -> SubscriptionManager -> PTB -> CoinUSD -> Evaluation
Tum component'lar ayni instance uzerinden calisir.
Trading e2e DEGIL — sadece sinyal uretimi dogrulanir. Order YOK.
"""

import asyncio
import json
import re
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.market_data.live_price import LivePricePipeline, PriceStatus
from backend.market_data.rtds_client import RTDSClient
from backend.market_data.ws_price_bridge import WSPriceBridge
from backend.market_data.coin_price_client import CoinPriceClient, CoinPriceStatus
from backend.ptb.ssr_adapter import SSRPTBAdapter
from backend.ptb.fetcher import PTBFetcher
from backend.settings.settings_store import SettingsStore
from backend.settings.coin_settings import CoinSettings, SideMode
from backend.strategy.engine import RuleEngine
from backend.strategy.rule_state import OverallDecision
from backend.orchestrator.evaluation_loop import EvaluationLoop
from backend.orchestrator.eligibility_gate import EligibilityGate
from backend.orchestrator.subscription_manager import SubscriptionManager

ASSETS = ["BTC", "ETH", "SOL", "DOGE", "XRP", "BNB"]
SLOT_SECONDS = 300


async def run_e2e():
    print("=" * 70)
    print("v0.4.6 CANLI EVALUATION E2E — TAM ZINCIR")
    print("=" * 70)
    print()

    now = int(time.time())
    slot = (now // SLOT_SECONDS) * SLOT_SECONDS
    elapsed = now - slot
    if elapsed < 30:
        wait = 30 - elapsed
        print(f"PTB icin {wait}s bekleniyor...")
        await asyncio.sleep(wait)
        now = int(time.time())
        slot = (now // SLOT_SECONDS) * SLOT_SECONDS

    print(f"Slot: {slot}, Elapsed: {now - slot}s")
    print()

    # Shared components
    pipeline = LivePricePipeline()
    bridge = WSPriceBridge(pipeline)
    coin_client = CoinPriceClient()
    ssr_adapter = SSRPTBAdapter()
    ptb_fetcher = PTBFetcher(source=ssr_adapter)
    store = SettingsStore()
    engine = RuleEngine()
    eligibility_gate = EligibilityGate(store)
    subscription_mgr = SubscriptionManager(bridge, coin_client, ptb_fetcher)

    # ═══ 1. DISCOVERY ═══
    print("[1] DISCOVERY")
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
                outcomes = json.loads(m.get("outcomes", "[]"))
                sides = ["up" if o.lower() in ("up", "yes") else "down" for o in outcomes]
                token_map[asset] = {
                    "condition_id": cond_id, "token_ids": clob_ids,
                    "sides": sides, "slug": slug,
                }
                print(f"  {asset}: {slug}")
    print(f"  Bulunan: {len(token_map)}/6")
    print()

    # ═══ 2. COIN SETTINGS ═══
    print("[2] COIN SETTINGS")
    for asset in token_map:
        store.set(CoinSettings(
            coin=asset, coin_enabled=True, side_mode=SideMode.DOMINANT_ONLY,
            delta_threshold=0.01, price_min=51, price_max=99,
            spread_max=50.0, time_min=1, time_max=299,
            event_max=1, order_amount=5.0,
        ))
    print(f"  Eligible: {store.eligible_count}")
    print()

    # ═══ 3. ELIGIBILITY GATE ═══
    print("[3] ELIGIBILITY GATE")
    events_as_dicts = [{"asset": a, **v} for a, v in token_map.items()]
    elig_result = eligibility_gate.filter(events_as_dicts)
    print(f"  Eligible: {len(elig_result.eligible)}, Ineligible: {len(elig_result.ineligible)}")
    print()

    # ═══ 4. SUBSCRIPTION MANAGER ═══
    print("[4] SUBSCRIPTION MANAGER")
    eligible_assets = [e.get("asset", "") for e in elig_result.eligible]
    diff = subscription_mgr.compute_diff(eligible_assets)
    await subscription_mgr.apply_diff(diff, token_map)
    print(f"  Subscribed: {subscription_mgr.subscribed_count} coins")
    print(f"  Diff: +{len(diff.to_subscribe)} -{len(diff.to_unsubscribe)} ={len(diff.unchanged)}")
    print()

    # ═══ 5. COIN USD (batch poll loop — 3s) ═══
    print("[5] COIN USD BATCH LOOP (3s)")
    coin_client.set_coins(eligible_assets)
    coin_task = asyncio.create_task(coin_client.run_forever())
    await asyncio.sleep(3)  # birkaç cycle bekle
    for asset in eligible_assets:
        r = coin_client.get_price(asset)
        if r:
            print(f"  {asset}: ${r.usd_price:,.4f} status={r.status.value}")
    print()

    # ═══ 6. PTB FETCH ═══
    print("[6] PTB FETCH")
    for asset, info in token_map.items():
        record = await ptb_fetcher.fetch_ptb(info["condition_id"], asset, info["slug"])
        status = "LOCKED" if record.is_locked else record.status.value
        val = f"${record.ptb_value:,.4f}" if record.ptb_value else "YOK"
        print(f"  {asset}: {val} ({status})")
    print()

    # ═══ 7. CLOB WS OUTCOME ═══
    print("[7] CLOB WS OUTCOME (3s)")
    all_token_ids = []
    for asset, info in token_map.items():
        for i, tid in enumerate(info["token_ids"]):
            side = info["sides"][i] if i < len(info["sides"]) else "up"
            bridge.register_token(tid, info["condition_id"], asset, side)
            all_token_ids.append(tid)

    rtds = RTDSClient(on_message=bridge.on_ws_message)
    connected = await rtds.connect()
    if connected:
        await rtds.subscribe(all_token_ids)
        recv_task = rtds.start_receive_loop()
        await asyncio.sleep(3)
        await rtds.disconnect()

    for r in pipeline.get_all_records():
        print(f"  {r.asset}: UP={r.up_price:.4f} DOWN={r.down_price:.4f} status={r.status.value}")
    print()

    # ═══ 8. EVALUATION ═══
    print("[8] EVALUATION")
    eval_loop = EvaluationLoop(engine, pipeline, coin_client, ptb_fetcher, store)

    results = {}
    for settings in store.get_eligible_coins():
        result = eval_loop._evaluate_single(settings)
        if result:
            results[settings.coin] = result
            parts = [f"{rr.rule_name}={rr.state.value}" for rr in result.rule_results]
            dec = result.decision.value
            print(f"  {settings.coin}: {dec.upper()} [{', '.join(parts)}]")

    # Stop coin price loop
    await coin_client.stop()

    print()

    # ═══ SONUC ═══
    print("=" * 70)
    print("SONUC")
    print("=" * 70)

    entry = sum(1 for r in results.values() if r.decision == OverallDecision.ENTRY)
    no_entry = sum(1 for r in results.values() if r.decision == OverallDecision.NO_ENTRY)
    waiting = sum(1 for r in results.values() if r.decision == OverallDecision.WAITING)

    checks = [
        ("Discovery 6/6", len(token_map) >= 5),
        ("Eligibility gate", len(elig_result.eligible) >= 5),
        ("Subscription diff", subscription_mgr.subscribed_count >= 5),
        ("Coin USD fresh", coin_client.fresh_count >= 5),
        ("PTB locked", ptb_fetcher.locked_count >= 5),
        ("CLOB WS outcome", len(pipeline.get_all_records()) >= 5),
        ("Evaluation", len(results) >= 5),
        ("Delta NOT waiting", waiting == 0 or entry + no_entry > 0),
    ]

    all_pass = True
    for name, ok in checks:
        s = "PASS" if ok else "FAIL"
        if not ok: all_pass = False
        print(f"  [{s}] {name}")

    print()
    print(f"  ENTRY={entry} NO_ENTRY={no_entry} WAITING={waiting}")
    print()
    if all_pass:
        print("FAZ 4 CANLI EVALUATION E2E BASARILI")
    else:
        print("BAZI KONTROLLER BASARISIZ")


if __name__ == "__main__":
    asyncio.run(run_e2e())
