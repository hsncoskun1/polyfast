"""Outcome price canli benchmark — CLOB WS vs CLOB REST vs Polymarket UI."""
import asyncio
import json
import time
import re
import sys
import os
import statistics
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import websockets
import httpx


# ══════════════════════════════════════════════════════════════
# EVRE 1 — KAYNAK HARITASI
# ══════════════════════════════════════════════════════════════

async def get_test_events():
    """Discovery'den current BTC + ETH event bul."""
    from backend.auth_clients.public_client import PublicMarketClient
    from backend.discovery.engine import DiscoveryEngine

    client = PublicMarketClient(timeout_seconds=15, retry_max=2)
    engine = DiscoveryEngine(client)
    result = await engine.scan()
    now = int(time.time())

    events = {}
    for e in result.events:
        asset = e.asset.upper()
        if asset in events:
            continue
        m = re.search(r'-(\d{10,})$', e.slug)
        if m:
            ts = int(m.group(1))
            if (ts - 300) <= now < ts:
                events[asset] = {
                    'slug': e.slug,
                    'condition_id': e.condition_id,
                    'token_up': e.clob_token_ids[0] if len(e.clob_token_ids) > 0 else '',
                    'token_down': e.clob_token_ids[1] if len(e.clob_token_ids) > 1 else '',
                    'outcomes': list(e.outcomes),
                }
    return events


# ══════════════════════════════════════════════════════════════
# KAYNAK A: CLOB WS Market Channel
# ══════════════════════════════════════════════════════════════

async def measure_clob_ws(events, duration_sec=30):
    """CLOB WS market channel'dan outcome price olc."""
    url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

    all_tokens = []
    token_map = {}  # token_id -> (asset, side)
    for asset, info in events.items():
        t_up = info['token_up']
        t_down = info['token_down']
        all_tokens.extend([t_up, t_down])
        token_map[t_up] = (asset, 'UP')
        token_map[t_down] = (asset, 'DOWN')

    # Per-token tracking
    updates = {t: [] for t in all_tokens}  # token -> [(timestamp_ms, best_bid, best_ask)]
    msg_count = 0
    routed = 0
    skipped = 0

    try:
        ws = await websockets.connect(url, ping_interval=None, close_timeout=3)

        # Subscribe with custom_feature_enabled
        sub_msg = json.dumps({
            "assets_ids": all_tokens,
            "type": "market",
            "custom_feature_enabled": True,
        })
        await ws.send(sub_msg)

        t0 = time.time()
        while time.time() - t0 < duration_sec:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=0.1)
                msg_count += 1
                data = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode())

                def process_item(item):
                    nonlocal routed, skipped
                    aid = item.get('asset_id', '')
                    if aid not in token_map:
                        skipped += 1
                        return
                    bb = item.get('best_bid')
                    ba = item.get('best_ask')
                    if bb is not None and ba is not None:
                        try:
                            updates[aid].append((time.time() * 1000, float(bb), float(ba)))
                            routed += 1
                        except (ValueError, TypeError):
                            pass

                if isinstance(data, list):
                    for item in data:
                        # Book snapshot
                        aid = item.get('asset_id', '')
                        bids = item.get('bids', [])
                        asks = item.get('asks', [])
                        if aid in token_map and bids and asks:
                            try:
                                bb = max(float(b['price']) for b in bids if b.get('price'))
                                ba = min(float(a['price']) for a in asks if a.get('price'))
                                updates[aid].append((time.time() * 1000, bb, ba))
                                routed += 1
                            except (ValueError, TypeError, KeyError):
                                pass
                elif isinstance(data, dict):
                    et = data.get('event_type', '')
                    if et in ('price_change', 'last_trade_price'):
                        for pc in data.get('price_changes', []):
                            process_item(pc)
                    elif et == 'best_bid_ask':
                        process_item(data)
                    else:
                        process_item(data)

            except asyncio.TimeoutError:
                continue

        await ws.close()
    except Exception as e:
        print(f"  WS ERROR: {e}")

    return updates, msg_count, routed, skipped


# ══════════════════════════════════════════════════════════════
# KAYNAK B: CLOB REST Midpoint Polling
# ══════════════════════════════════════════════════════════════

async def measure_clob_rest(events, duration_sec=30, poll_interval_ms=200):
    """CLOB REST midpoint endpoint'i ile polling olc."""
    url = "https://clob.polymarket.com/midpoints"

    token_list = []
    token_map = {}
    for asset, info in events.items():
        t_up = info['token_up']
        t_down = info['token_down']
        token_list.extend([t_up, t_down])
        token_map[t_up] = (asset, 'UP')
        token_map[t_down] = (asset, 'DOWN')

    updates = {t: [] for t in token_list}
    request_count = 0
    error_count = 0

    body = [{"token_id": t} for t in token_list]

    async with httpx.AsyncClient(timeout=5) as client:
        t0 = time.time()
        while time.time() - t0 < duration_sec:
            try:
                resp = await client.post(url, json=body)
                request_count += 1
                if resp.status_code == 200:
                    data = resp.json()
                    now_ms = time.time() * 1000
                    for tid in token_list:
                        val = data.get(tid)
                        if val is not None:
                            try:
                                mid = float(val)
                                updates[tid].append((now_ms, mid, mid))  # midpoint = bid = ask
                            except (ValueError, TypeError):
                                pass
                else:
                    error_count += 1
            except Exception:
                error_count += 1

            await asyncio.sleep(poll_interval_ms / 1000.0)

    return updates, request_count, error_count


# ══════════════════════════════════════════════════════════════
# KAYNAK C: CLOB REST Price (best bid/ask ayri)
# ══════════════════════════════════════════════════════════════

async def measure_clob_rest_price(events, duration_sec=30, poll_interval_ms=500):
    """CLOB REST price endpoint — best bid + best ask ayri."""
    base = "https://clob.polymarket.com"

    token_list = []
    token_map = {}
    for asset, info in events.items():
        t_up = info['token_up']
        t_down = info['token_down']
        token_list.extend([t_up, t_down])
        token_map[t_up] = (asset, 'UP')
        token_map[t_down] = (asset, 'DOWN')

    updates = {t: [] for t in token_list}
    request_count = 0
    error_count = 0

    async with httpx.AsyncClient(timeout=5) as client:
        t0 = time.time()
        while time.time() - t0 < duration_sec:
            now_ms = time.time() * 1000
            for tid in token_list:
                try:
                    # buy side = best ask (karsi tarafin en iyi fiyati)
                    r_buy = await client.get(f"{base}/price", params={"token_id": tid, "side": "buy"})
                    r_sell = await client.get(f"{base}/price", params={"token_id": tid, "side": "sell"})
                    request_count += 2
                    if r_buy.status_code == 200 and r_sell.status_code == 200:
                        buy_p = float(r_buy.json().get("price", 0))
                        sell_p = float(r_sell.json().get("price", 0))
                        updates[tid].append((now_ms, sell_p, buy_p))  # sell=bid, buy=ask
                    else:
                        error_count += 1
                except Exception:
                    error_count += 1

            await asyncio.sleep(poll_interval_ms / 1000.0)

    return updates, request_count, error_count


# ══════════════════════════════════════════════════════════════
# ANALIZ
# ══════════════════════════════════════════════════════════════

def analyze_updates(updates, token_map, label):
    """Update listesinden metrik hesapla."""
    print(f"\n--- {label} ---")

    for tid, data_list in updates.items():
        if tid not in token_map:
            continue
        asset, side = token_map[tid]
        n = len(data_list)
        if n < 2:
            print(f"  {asset} {side}: {n} update (yetersiz)")
            continue

        # Fiyat degisimi olan update'ler
        price_changes = []
        intervals = []
        for i in range(1, n):
            dt = data_list[i][0] - data_list[i-1][0]
            intervals.append(dt)
            if data_list[i][1] != data_list[i-1][1] or data_list[i][2] != data_list[i-1][2]:
                price_changes.append(i)

        avg_int = statistics.mean(intervals) if intervals else 0
        med_int = statistics.median(intervals) if intervals else 0
        min_int = min(intervals) if intervals else 0
        max_int = max(intervals) if intervals else 0

        last_bid = data_list[-1][1]
        last_ask = data_list[-1][2]
        mid = (last_bid + last_ask) / 2 if last_ask > 0 else last_bid

        print(f"  {asset} {side}: {n} updates | avg={avg_int:.0f}ms med={med_int:.0f}ms min={min_int:.0f}ms max={max_int:.0f}ms")
        print(f"    last: bid={last_bid:.4f} ask={last_ask:.4f} mid={mid:.4f}")
        print(f"    price_changes: {len(price_changes)}")


async def main():
    print("=" * 70)
    print("OUTCOME PRICE CANLI BENCHMARK")
    print("=" * 70)
    print()

    # EVRE 1: Test eventleri bul
    events = await get_test_events()
    test_coins = ['BTC', 'ETH']
    test_events = {k: v for k, v in events.items() if k in test_coins}

    if not test_events:
        print("HATA: Current event bulunamadi")
        return

    now = int(time.time())
    slot_start = (now // 300) * 300
    slot_remain = slot_start + 300 - now

    print(f"Slot: start={slot_start} remain={slot_remain}s")
    print(f"Test coinleri: {list(test_events.keys())}")
    for asset, info in test_events.items():
        print(f"  {asset}: slug={info['slug']}")
        print(f"    UP token:   {info['token_up'][:24]}...")
        print(f"    DOWN token: {info['token_down'][:24]}...")
    print()

    token_map = {}
    for asset, info in test_events.items():
        token_map[info['token_up']] = (asset, 'UP')
        token_map[info['token_down']] = (asset, 'DOWN')

    duration = 30  # 30 saniye

    # EVRE 2A: CLOB WS
    print(f"[1/3] CLOB WS Market Channel ({duration}s)...")
    ws_updates, ws_msgs, ws_routed, ws_skipped = await measure_clob_ws(test_events, duration)
    print(f"  msgs={ws_msgs} routed={ws_routed} skipped={ws_skipped}")
    analyze_updates(ws_updates, token_map, "CLOB WS Market Channel")

    # Son fiyatlari kaydet — karsilastirma icin
    ws_final = {}
    for tid, data in ws_updates.items():
        if tid in token_map and data:
            asset, side = token_map[tid]
            bid, ask = data[-1][1], data[-1][2]
            mid = (bid + ask) / 2
            ws_final[(asset, side)] = {'bid': bid, 'ask': ask, 'mid': mid}

    print()

    # EVRE 2B: CLOB REST Midpoint (200ms poll)
    print(f"[2/3] CLOB REST Midpoint Polling 200ms ({duration}s)...")
    rest_updates, rest_reqs, rest_errs = await measure_clob_rest(test_events, duration, 200)
    print(f"  requests={rest_reqs} errors={rest_errs}")
    analyze_updates(rest_updates, token_map, "CLOB REST Midpoint (200ms)")

    rest_final = {}
    for tid, data in rest_updates.items():
        if tid in token_map and data:
            asset, side = token_map[tid]
            rest_final[(asset, side)] = {'mid': data[-1][1]}

    print()

    # EVRE 2C: CLOB REST Price (500ms poll — her coin ayri istek)
    print(f"[3/3] CLOB REST Price bid/ask 500ms ({duration}s)...")
    price_updates, price_reqs, price_errs = await measure_clob_rest_price(test_events, duration, 500)
    print(f"  requests={price_reqs} errors={price_errs}")
    analyze_updates(price_updates, token_map, "CLOB REST Price (500ms)")

    price_final = {}
    for tid, data in price_updates.items():
        if tid in token_map and data:
            asset, side = token_map[tid]
            bid, ask = data[-1][1], data[-1][2]
            mid = (bid + ask) / 2
            price_final[(asset, side)] = {'bid': bid, 'ask': ask, 'mid': mid}

    # EVRE 3: Polymarket UI karsilastirmasi (REST son degeri referans)
    print()
    print("=" * 70)
    print("KARSILASTIRMA TABLOSU")
    print("=" * 70)
    print()

    header = f"{'COIN':<5} {'SIDE':<5} | {'WS bid':<8} {'WS ask':<8} {'WS mid':<8} | {'REST mid':<9} | {'Price bid':<9} {'Price ask':<9} | {'Match?'}"
    print(header)
    print("-" * len(header))

    for asset in test_coins:
        for side in ['UP', 'DOWN']:
            key = (asset, side)
            ws = ws_final.get(key, {})
            rest = rest_final.get(key, {})
            price = price_final.get(key, {})

            ws_bid = ws.get('bid', 0)
            ws_ask = ws.get('ask', 0)
            ws_mid = ws.get('mid', 0)
            rest_mid = rest.get('mid', 0)
            p_bid = price.get('bid', 0)
            p_ask = price.get('ask', 0)

            # Match: WS mid vs REST mid fark
            diff = abs(ws_mid - rest_mid) if ws_mid > 0 and rest_mid > 0 else -1
            match = "OK" if diff >= 0 and diff < 0.005 else f"DIFF={diff:.4f}" if diff >= 0 else "N/A"

            print(f"{asset:<5} {side:<5} | {ws_bid:<8.4f} {ws_ask:<8.4f} {ws_mid:<8.4f} | {rest_mid:<9.4f} | {p_bid:<9.4f} {p_ask:<9.4f} | {match}")

    print()
    print("=" * 70)
    print("BENCHMARK TAMAMLANDI")
    print("=" * 70)


if __name__ == '__main__':
    asyncio.run(main())
