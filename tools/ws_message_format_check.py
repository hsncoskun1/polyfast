"""Check WS message formats to understand what we receive."""
import asyncio
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import websockets

ASSETS = ["BTC", "ETH", "SOL"]

async def main():
    now = int(time.time())
    end_ts = ((now // 300) + 1) * 300

    all_tokens = []
    async with httpx.AsyncClient(timeout=10) as client:
        for asset in ASSETS:
            slug = f"{asset.lower()}-updown-5m-{end_ts}"
            resp = await client.get("https://gamma-api.polymarket.com/markets", params={"slug": slug})
            if resp.status_code == 200:
                markets = resp.json()
                if markets:
                    clob_ids = json.loads(markets[0].get("clobTokenIds", "[]"))
                    all_tokens.extend(clob_ids)
                    print(f"{asset}: {len(clob_ids)} tokens")

    print(f"\nTotal tokens: {len(all_tokens)}")
    print("Connecting to WS...")

    ws = await websockets.connect("wss://ws-subscriptions-clob.polymarket.com/ws/market")
    sub_msg = json.dumps({"assets_ids": all_tokens, "type": "market", "custom_feature_enabled": True})
    await ws.send(sub_msg)

    # Collect 5 seconds of messages and show format
    formats_seen = {}
    start = time.time()
    count = 0
    while time.time() - start < 5:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=1)
            data = json.loads(raw)
            count += 1

            # Show first 5 messages in full
            if count <= 5:
                print(f"\n--- Message #{count} ---")
                if isinstance(data, list):
                    for item in data:
                        print(f"  Type: list item")
                        print(f"  Keys: {list(item.keys())}")
                        print(f"  Content: {json.dumps(item)[:300]}")
                        et = item.get("event_type", "NONE")
                        formats_seen[et] = formats_seen.get(et, 0) + 1
                elif isinstance(data, dict):
                    print(f"  Type: dict")
                    print(f"  Keys: {list(data.keys())}")
                    print(f"  Content: {json.dumps(data)[:300]}")
                    et = data.get("event_type", "NONE")
                    formats_seen[et] = formats_seen.get(et, 0) + 1
            else:
                if isinstance(data, list):
                    for item in data:
                        et = item.get("event_type", "NONE")
                        formats_seen[et] = formats_seen.get(et, 0) + 1
                elif isinstance(data, dict):
                    et = data.get("event_type", "NONE")
                    formats_seen[et] = formats_seen.get(et, 0) + 1
        except asyncio.TimeoutError:
            continue

    await ws.close()

    print(f"\n\nTotal messages: {count}")
    print(f"Event types seen: {formats_seen}")

asyncio.run(main())
