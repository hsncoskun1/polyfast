"""Debug: pipeline current vs upcoming records."""
import asyncio, time, sys, os, re, functools
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

    # 15s bekle
    for i in range(6):
        await asyncio.sleep(2.5)
        elapsed = (i + 1) * 2.5
        now = int(time.time())
        slot_start = (now // 300) * 300
        slot_end = slot_start + 300

        # Pipeline records
        all_rec = orch.pipeline.get_all_records()
        btc_recs = [r for r in all_rec if r.asset.upper() == 'BTC']

        # Registry current
        current_cid = orch.evaluation_loop._find_current_slot_condition_id('BTC')

        print(f"[{elapsed:.0f}s] now={now} slot={slot_start}-{slot_end} remain={slot_end-now}s")
        print(f"  pipeline BTC records: {len(btc_recs)}")
        for rec in btc_recs:
            reg = orch.registry.get_by_condition_id(rec.condition_id)
            slug = reg.slug if reg else '?'
            m = re.search(r'-(\d{10,})$', slug)
            end_ts = int(m.group(1)) if m else 0
            is_current = (end_ts - 300) <= now < end_ts if end_ts else False
            label = 'CURRENT' if is_current else 'UPCOMING'
            print(f"    [{label}] cid={rec.condition_id[:16]}... bid={rec.up_bid:.4f} {slug}")
        print(f"  current_cid: {current_cid[:16]}..." if current_cid else "  current_cid: NONE")
        if current_cid:
            pipe = orch.pipeline.get_record(current_cid)
            print(f"  pipeline[current_cid]: {'FOUND bid=' + f'{pipe.up_bid:.4f}' if pipe else 'NONE'}")
        print()

    await orch.stop()
    await close_db()

if __name__ == '__main__':
    asyncio.run(main())
