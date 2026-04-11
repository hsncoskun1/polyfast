"""Debug: event_map -> subscription -> bridge -> pipeline -> dispatch tam zincir."""
import asyncio, time, re, sys, os, functools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
print = functools.partial(print, flush=True)

async def main():
    from backend.persistence.database import init_db, close_db
    from backend.persistence.migrations import run_migrations
    from backend.orchestrator.wiring import Orchestrator
    from backend.persistence.credential_persistence import load_encrypted
    from backend.settings.coin_settings import CoinSettings

    db = await init_db()
    await run_migrations(db)
    orch = Orchestrator()
    creds = load_encrypted()
    orch.credential_store.load(creds)
    orch.settings_store.set(CoinSettings(coin='BTC', coin_enabled=True, delta_threshold=0.00001,
                                          price_min=51, price_max=99, time_min=10, time_max=290,
                                          order_amount=1.0, event_max=1))
    await orch.start()
    bal = await orch.clob_client.get_balance()
    if bal:
        orch.balance_manager.update(bal['available'], bal.get('total', bal['available']))
        orch.trading_enabled = True

    for i in range(8):
        await asyncio.sleep(3)
        now = int(time.time())
        slot_start = (now // 300) * 300
        slot_end = slot_start + 300

        print(f"[{(i+1)*3}s] now={now} slot={slot_start}-{slot_end} remain={slot_end-now}s")
        print(f"  Live event: https://polymarket.com/event/btc-updown-5m-{slot_start}")

        # Active events (subscription)
        ae = orch.subscription_manager._active_events
        for asset, cid in ae.items():
            if asset == 'BTC':
                reg = orch.registry.get_by_condition_id(cid)
                slug = reg.slug if reg else '?'
                m = re.search(r'-(\d{10,})$', slug)
                end_ts = int(m.group(1)) if m else 0
                event_start = end_ts - 300
                is_current = event_start <= now < end_ts
                print(f"  active_event: cid={cid[:16]}... slug={slug} [{('CURRENT' if is_current else 'WRONG!')}]")
                print(f"    event_start={event_start} event_end={end_ts}")

        # Bridge routes
        for tid, route in orch.bridge._token_routes.items():
            if route.asset.upper() == 'BTC':
                reg = orch.registry.get_by_condition_id(route.condition_id)
                slug = reg.slug if reg else '?'
                m = re.search(r'-(\d{10,})$', slug)
                end_ts = int(m.group(1)) if m else 0
                event_start = end_ts - 300
                is_current = event_start <= now < end_ts
                print(f"  bridge: {route.side} cid={route.condition_id[:16]}... [{('CURRENT' if is_current else 'WRONG!')}]")

        # Pipeline
        for rec in orch.pipeline.get_all_records():
            if rec.asset.upper() == 'BTC':
                reg = orch.registry.get_by_condition_id(rec.condition_id)
                slug = reg.slug if reg else '?'
                m = re.search(r'-(\d{10,})$', slug)
                end_ts = int(m.group(1)) if m else 0
                event_start = end_ts - 300
                is_current = event_start <= now < end_ts
                print(f"  pipeline: cid={rec.condition_id[:16]}... bid={rec.up_bid:.4f} [{('CURRENT' if is_current else 'WRONG!')}]")

        # _find_current
        ccid = orch.evaluation_loop._find_current_slot_condition_id('BTC')
        if ccid:
            reg = orch.registry.get_by_condition_id(ccid)
            slug = reg.slug if reg else '?'
            print(f"  find_current: {ccid[:16]}... slug={slug}")
        else:
            print(f"  find_current: NONE")

        print()

    await orch.stop()
    await close_db()

if __name__ == '__main__':
    asyncio.run(main())
