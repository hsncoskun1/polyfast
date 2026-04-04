"""v0.3.4 CANLI DOGRULAMA — WS > LivePricePipeline ucu uca test.

GPT direktifi: gercek Polymarket WS ile canli dogrulama yap.
Test edilen: subscribe, veri akisi, WSPriceBridge routing,
LivePricePipeline.update_from_ws(), stale handling, reconnect.

Bu script production kodu KULLANIR (import eder), mock yoktur.
"""

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from backend.market_data.rtds_client import RTDSClient, ConnectionState
from backend.market_data.live_price import LivePricePipeline, PriceSource, PriceStatus
from backend.market_data.ws_price_bridge import WSPriceBridge
from backend.market_data.mapping import MarketMapper, MarketSide

# 7 target assets
ASSETS = ["BTC", "ETH", "SOL", "DOGE", "XRP", "BNB", "MATIC"]


async def discover_current_events():
    """Find current 5M events via Gamma API slug calculation."""
    now = int(time.time())
    end_ts = ((now // 300) + 1) * 300
    results = []

    async with httpx.AsyncClient(timeout=10) as client:
        for asset in ASSETS:
            slug = f"{asset.lower()}-updown-5m-{end_ts}"
            try:
                resp = await client.get(
                    "https://gamma-api.polymarket.com/markets",
                    params={"slug": slug},
                )
                if resp.status_code == 200:
                    markets = resp.json()
                    if markets:
                        results.append((asset, slug, markets[0]))
            except Exception as e:
                print(f"    {asset} discovery hatasi: {e}")

    return results


async def run_live_validation():
    print("=" * 70)
    print("v0.3.4 CANLI DOGRULAMA — WS > LivePricePipeline")
    print("=" * 70)
    print()

    # ─── 1. Discovery ───
    print("[1] Discovery — aktif 5M eventleri bulma...")
    found_events = await discover_current_events()
    print(f"    Bulunan event sayisi: {len(found_events)}")

    if not found_events:
        print("    HATA: Hic aktif event bulunamadi!")
        return

    for asset, slug, _ in found_events:
        print(f"    - {asset}: {slug}")

    # ─── 2. Mapping ───
    print()
    print("[2] Mapping — token ID'leri cikarma...")
    mapper = MarketMapper()
    all_token_ids = []
    bridge_routes = []

    for asset, slug, market_data in found_events:
        condition_id = market_data.get("conditionId", "")
        clob_ids = market_data.get("clobTokenIds", "[]")
        outcomes = market_data.get("outcomes", "[]")

        if isinstance(clob_ids, str):
            clob_ids = json.loads(clob_ids)
        if isinstance(outcomes, str):
            outcomes = json.loads(outcomes)

        if not condition_id or not clob_ids:
            print(f"    {asset}: mapping basarisiz (conditionId/clobTokenIds eksik)")
            continue

        for i, token_id in enumerate(clob_ids):
            outcome = outcomes[i] if i < len(outcomes) else ""
            side = "up" if outcome.lower() in ("up", "yes") else "down"
            all_token_ids.append(token_id)
            bridge_routes.append((token_id, condition_id, asset, side))
            print(f"    {asset} {side}: {token_id[:24]}...")

    print(f"    Toplam token: {len(all_token_ids)}")

    if not all_token_ids:
        print("    HATA: Hic token ID bulunamadi!")
        return

    # ─── 3. Setup pipeline + bridge ───
    print()
    print("[3] Pipeline + Bridge kurulumu...")
    pipeline = LivePricePipeline(stale_threshold_sec=30)
    bridge = WSPriceBridge(pipeline)

    for token_id, cond_id, asset, side in bridge_routes:
        bridge.register_token(token_id, cond_id, asset, side)

    print(f"    Bridge registered tokens: {bridge.registered_count}")
    print(f"    Pipeline records (bos): {len(pipeline.get_all_records())}")

    # ─── 4. Connect + Subscribe + Receive ───
    print()
    print("[4] WS baglanti + subscribe + veri alma (15 saniye)...")

    rtds = RTDSClient(on_message=bridge.on_ws_message)

    connect_start = time.monotonic()
    connected = await rtds.connect()
    connect_ms = (time.monotonic() - connect_start) * 1000
    print(f"    Baglanti: {'BASARILI' if connected else 'BASARISIZ'} ({connect_ms:.0f}ms)")

    if not connected:
        print("    HATA: WS baglantisi kurulamadi!")
        return

    # Subscribe
    subscribe_payload = {
        "assets_ids": all_token_ids,
        "type": "market",
        "custom_feature_enabled": True,
    }
    print(f"    Subscribe payload: {len(all_token_ids)} token")

    sub_start = time.monotonic()
    sub_ok = await rtds.subscribe(all_token_ids)
    sub_ms = (time.monotonic() - sub_start) * 1000
    print(f"    Subscribe: {'BASARILI' if sub_ok else 'BASARISIZ'} ({sub_ms:.0f}ms)")

    # Start receive loop
    recv_task = rtds.start_receive_loop()

    # Wait for first message
    first_msg_time = None
    wait_start = time.monotonic()

    while (time.monotonic() - wait_start) < 5:
        if rtds.total_messages_received > 0:
            first_msg_time = (time.monotonic() - wait_start) * 1000
            break
        await asyncio.sleep(0.05)

    if first_msg_time:
        print(f"    Ilk mesaj: {first_msg_time:.0f}ms sonra geldi")
    else:
        print("    UYARI: 5 saniye icinde mesaj gelmedi!")

    # Collect for 15 seconds
    print(f"    15 saniye veri toplaniyor...")
    await asyncio.sleep(15)

    total_msgs = rtds.total_messages_received
    total_routed = bridge.total_routed
    total_skipped = bridge.total_skipped
    print(f"    Toplam WS mesaj: {total_msgs}")
    print(f"    Bridge routed: {total_routed}")
    print(f"    Bridge skipped: {total_skipped}")

    # ─── 5. Pipeline State Check ───
    print()
    print("[5] Pipeline durumu...")
    records = pipeline.get_all_records()
    fresh_count = pipeline.fresh_count
    stale_count = pipeline.stale_count
    invalid_count = pipeline.invalid_count

    print(f"    Record sayisi: {len(records)}")
    print(f"    FRESH: {fresh_count}")
    print(f"    STALE: {stale_count}")
    print(f"    INVALID: {invalid_count}")
    print()

    for record in records:
        age = f"{record.age_seconds:.1f}s" if record.age_seconds is not None else "N/A"
        print(f"    {record.asset}:")
        print(f"      up_price={record.up_price:.4f}  down_price={record.down_price:.4f}")
        print(f"      spread={record.spread:.4f}  best_bid={record.best_bid:.4f}  best_ask={record.best_ask:.4f}")
        print(f"      status={record.status.value}  source={record.source}  age={age}")

    # ─── 6. Source Verification ───
    print()
    print("[6] Source dogrulama...")
    ws_sourced = sum(1 for r in records if r.source == PriceSource.RTDS_WS.value)
    gamma_sourced = sum(1 for r in records if r.source == PriceSource.GAMMA_OUTCOME_PRICES.value)
    print(f"    WS kaynak: {ws_sourced}/{len(records)}")
    print(f"    Gamma kaynak: {gamma_sourced}/{len(records)}")
    print(f"    WS authoritative: {'EVET' if ws_sourced == len(records) else 'HAYIR'}")

    # ─── 7. Stale Handling Test ───
    print()
    print("[7] Stale handling testi — WS kapatma ve gozlem...")
    await rtds.disconnect()
    print(f"    WS disconnected. Connection state: {rtds.state.value}")

    # Wait for stale threshold
    print(f"    30s bekleniyor (stale threshold)...")
    await asyncio.sleep(32)

    stale_records = [r for r in pipeline.get_all_records() if r.status == PriceStatus.STALE]
    print(f"    STALE record sayisi: {len(stale_records)}/{len(records)}")

    health_incidents = pipeline.get_health_incidents()
    print(f"    Health incidents: {len(health_incidents)}")
    for inc in health_incidents[:3]:
        print(f"      - {inc.message}")

    # ─── 8. Reconnect + Resubscribe Test ───
    print()
    print("[8] Reconnect + resubscribe testi...")
    reconnect_start = time.monotonic()
    reconnected = await rtds.connect()
    reconnect_ms = (time.monotonic() - reconnect_start) * 1000
    print(f"    Reconnect: {'BASARILI' if reconnected else 'BASARISIZ'} ({reconnect_ms:.0f}ms)")

    if reconnected:
        resub_ok = await rtds.subscribe(all_token_ids)
        print(f"    Resubscribe: {'BASARILI' if resub_ok else 'BASARISIZ'}")

        # Start receive again
        recv_task = rtds.start_receive_loop()
        msgs_before = rtds.total_messages_received

        print(f"    5s veri bekleniyor...")
        await asyncio.sleep(5)

        msgs_after = rtds.total_messages_received
        new_msgs = msgs_after - msgs_before
        print(f"    Reconnect sonrasi yeni mesaj: {new_msgs}")

        # Check STALE -> FRESH
        fresh_after = sum(1 for r in pipeline.get_all_records() if r.status == PriceStatus.FRESH)
        print(f"    STALE > FRESH donus: {fresh_after}/{len(records)} record FRESH")

    # Cleanup
    await rtds.disconnect()

    # ─── 9. Mesaj Frekansi ───
    print()
    print("[9] Mesaj frekansi hesaplama...")
    if total_msgs > 0:
        freq = total_msgs / 15.0
        print(f"    Toplam mesaj (15s): {total_msgs}")
        print(f"    Frekans: ~{freq:.1f} mesaj/saniye")
    else:
        print(f"    Mesaj yok — frekans hesaplanamadi")

    # ─── SONUC ───
    print()
    print("=" * 70)
    print("CANLI DOGRULAMA SONUC")
    print("=" * 70)

    checks = [
        ("WS baglanti", connected),
        ("Subscribe basarili", sub_ok),
        ("Mesaj alindi (>0)", total_msgs > 0),
        ("Bridge routing calisiyor", total_routed > 0),
        ("Pipeline record'lar var", len(records) > 0),
        ("Tum record'lar WS kaynak", ws_sourced == len(records)),
        ("Stale handling calisiyor", len(stale_records) > 0),
        ("Reconnect basarili", reconnected),
        ("STALE > FRESH donus", fresh_after > 0 if reconnected else False),
    ]

    all_pass = True
    for name, ok in checks:
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  [{status}] {name}")

    print()
    if all_pass:
        print("SONUC: TUM TESTLER GECTI — v0.3.4 canli dogrulama BASARILI")
    else:
        print("SONUC: BAZI TESTLER BASARISIZ")

    print()
    print("DETAY:")
    print(f"  Baglanti suresi: {connect_ms:.0f}ms")
    print(f"  Ilk mesaj gecikmesi: {first_msg_time:.0f}ms" if first_msg_time else "  Ilk mesaj: GELMEDI")
    print(f"  15s toplam mesaj: {total_msgs}")
    print(f"  Mesaj frekansi: ~{total_msgs/15:.1f}/s" if total_msgs else "  Mesaj frekansi: N/A")
    print(f"  Bridge routed/skipped: {total_routed}/{total_skipped}")
    print(f"  Test edilen asset sayisi: {len(records)}")
    print(f"  Reconnect suresi: {reconnect_ms:.0f}ms" if reconnected else "  Reconnect: BASARISIZ")

    # Print assets tested
    tested_assets = [r.asset for r in records]
    print(f"  Test edilen assetler: {', '.join(tested_assets)}")


if __name__ == "__main__":
    asyncio.run(run_live_validation())
