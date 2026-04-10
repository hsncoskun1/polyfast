"""PTB slug format analizi — TUM coinler."""
import asyncio, re, time, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

async def main():
    from backend.auth_clients.public_client import PublicMarketClient
    from backend.discovery.engine import DiscoveryEngine
    from backend.ptb.ssr_adapter import SSRPTBAdapter

    now = int(time.time())
    slot_start = (now // 300) * 300
    slot_end = slot_start + 300

    print(f"NOW={now}  slot_start={slot_start}  slot_end={slot_end}  remain={slot_end-now}s")
    print()

    client = PublicMarketClient(timeout_seconds=15, retry_max=2)
    engine = DiscoveryEngine(client)
    result = await engine.scan()

    # Her coin icin CURRENT event bul
    coins = {}
    for e in result.events:
        asset = e.asset.upper()
        m = re.search(r'-(\d{10,})$', e.slug)
        if not m:
            continue
        slug_ts = int(m.group(1))
        is_current = (slug_ts - 300) <= now < slug_ts
        if is_current and asset not in coins:
            coins[asset] = e.slug

    print(f"CURRENT eventler: {len(coins)} coin")
    print()

    adapter = SSRPTBAdapter(timeout_seconds=10)

    header = f"{'COIN':<6} | {'API_SLUG (end_ts)':<38} | {'api':<5} | {'START_SLUG':<38} | {'start':<5} | {'PTB_VALUE':<15}"
    print(header)
    print("-" * len(header))

    totals = {"api_ok": 0, "api_fail": 0, "start_ok": 0, "start_fail": 0}

    for asset in sorted(coins.keys()):
        api_slug = coins[asset]
        start_slug = f"{asset.lower()}-updown-5m-{slot_start}"

        r1 = await adapter.fetch_ptb(asset, api_slug)
        r2 = await adapter.fetch_ptb(asset, start_slug)

        s1 = "OK" if r1.success else "FAIL"
        s2 = "OK" if r2.success else "FAIL"
        val = f"${r2.value:,.2f}" if r2.success else ("$" + f"{r1.value:,.2f}" if r1.success else "---")

        if r1.success: totals["api_ok"] += 1
        else: totals["api_fail"] += 1
        if r2.success: totals["start_ok"] += 1
        else: totals["start_fail"] += 1

        print(f"{asset:<6} | {api_slug:<38} | {s1:<5} | {start_slug:<38} | {s2:<5} | {val}")

    total = len(coins)
    print()
    print("=== SONUC ===")
    print(f"Toplam coin: {total}")
    print(f"API slug (end_ts):     OK={totals['api_ok']}/{total}  FAIL={totals['api_fail']}/{total}")
    print(f"Start slug (start_ts): OK={totals['start_ok']}/{total}  FAIL={totals['start_fail']}/{total}")

if __name__ == "__main__":
    asyncio.run(main())
