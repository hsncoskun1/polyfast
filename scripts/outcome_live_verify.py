"""Live verification: CLOB WS outcome price -> pipeline -> evaluation."""
import asyncio, time, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

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
    orch.settings_store.set(CoinSettings(
        coin='BTC', coin_enabled=True,
        delta_threshold=0.00001, price_min=51, price_max=99,
        time_min=10, time_max=290, order_amount=1.0,
    ))
    orch.settings_store.set(CoinSettings(
        coin='ETH', coin_enabled=True,
        delta_threshold=0.00001, price_min=51, price_max=99,
        time_min=10, time_max=290, order_amount=1.0,
    ))

    await orch.start()
    bal = await orch.clob_client.get_balance()
    if bal:
        orch.balance_manager.update(bal['available'], bal.get('total', bal['available']))
        orch.trading_enabled = True

    print("=== OUTCOME PRICE LIVE VERIFY ===")
    print()

    # RTDS status
    print(f"RTDS connected: {orch.rtds_client.is_connected}")
    print(f"RTDS task alive: {orch._rtds_task is not None and not orch._rtds_task.done()}")
    print()

    for i in range(16):
        await asyncio.sleep(2.5)
        elapsed = (i + 1) * 2.5

        results = orch.evaluation_loop.get_last_results()
        search = orch.build_search_snapshot()

        for asset in ['BTC', 'ETH']:
            ev = results.get(asset)
            if not ev:
                continue

            d = ev.decision.value
            p = ev.pass_count
            f_ = ev.fail_count
            w = ev.waiting_count
            total = p + f_ + w

            # Pipeline per-side
            pipe = orch.pipeline.get_record_by_asset(asset)
            if pipe:
                ub = pipe.up_bid
                ua = pipe.up_ask
                db_ = pipe.down_bid
                da = pipe.down_ask
                fresh = pipe.status.value
            else:
                ub = ua = db_ = da = 0
                fresh = 'NONE'

            # Rule states
            price_st = delta_st = '?'
            for rr in ev.rule_results:
                if rr.rule_name == 'price':
                    price_st = rr.state.value
                elif rr.rule_name == 'delta':
                    delta_st = rr.state.value

            tile = next((t for t in search if t['coin'] == asset), None)
            pnl = tile['pnl_big'] if tile else '?'

            # Print compactly
            if i == 0 or i == 3 or i == 7 or i == 15 or (ub > 0 and d != 'waiting'):
                print(f"[{elapsed:5.1f}s] {asset}: {d} {p}/{total} price={price_st} delta={delta_st} tile={pnl}")
                if ub > 0 or db_ > 0:
                    mid_up = (ub + ua) / 2 if ua > 0 else ub
                    mid_dn = (db_ + da) / 2 if da > 0 else db_
                    print(f"         UP: bid={ub:.4f} ask={ua:.4f} mid={mid_up:.4f}")
                    print(f"         DN: bid={db_:.4f} ask={da:.4f} mid={mid_dn:.4f}")
                    print(f"         status={fresh} UP+DN bid={ub+db_:.4f}")
                else:
                    print(f"         pipeline={fresh}")

        if i == 0:
            print()

    # Final
    print()
    print("=== FINAL ===")
    print(f"RTDS connected: {orch.rtds_client.is_connected}")
    print(f"RTDS msgs: {orch.rtds_client.total_messages_received}")
    print(f"Bridge routed: {orch.bridge.total_routed}")
    print(f"Bridge skipped: {orch.bridge.total_skipped}")

    for asset in ['BTC', 'ETH']:
        ev = results.get(asset)
        if ev:
            print(f"\n{asset}: decision={ev.decision.value}")
            for rr in ev.rule_results:
                print(f"  {rr.rule_name}: {rr.state.value}")

    await orch.stop()
    await close_db()
    print("\nDone.")

if __name__ == '__main__':
    asyncio.run(main())
