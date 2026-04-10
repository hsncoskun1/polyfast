"""PTB fix final dogrulama — PTB + delta rule + search tile."""
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

    print("=== PTB FIX FINAL DOGRULAMA ===")
    print()

    for i in range(12):
        await asyncio.sleep(2.5)
        elapsed = (i + 1) * 2.5

        results = orch.evaluation_loop.get_last_results()
        search = orch.build_search_snapshot()

        changed = False
        for asset in ['BTC', 'ETH']:
            ev = results.get(asset)
            if not ev:
                continue
            d = ev.decision.value
            p = ev.pass_count
            f_ = ev.fail_count
            w = ev.waiting_count
            total = p + f_ + w

            # Delta rule
            delta_state = '?'
            delta_val = '?'
            for rr in ev.rule_results:
                if rr.rule_name == 'delta':
                    delta_state = rr.state.value
                    delta_val = rr.detail.get('live_value', '?')

            # Price rule
            price_state = '?'
            for rr in ev.rule_results:
                if rr.rule_name == 'price':
                    price_state = rr.state.value

            tile = next((t for t in search if t['coin'] == asset), None)
            pnl_big = tile['pnl_big'] if tile else '?'

            # PTB check
            ptb_rec = orch.ptb_fetcher.get_record_by_asset(asset)
            ptb_val = ptb_rec.ptb_value if ptb_rec and ptb_rec.is_locked else 0
            ptb_locked = ptb_rec.is_locked if ptb_rec else False

            # Coin USD
            coin_rec = orch.coin_client.get_price(asset)
            coin_usd = coin_rec.usd_price if coin_rec else 0

            if delta_state != 'waiting' or i == 0 or i == 11:
                changed = True
                delta_usd = abs(coin_usd - ptb_val) if coin_usd > 0 and ptb_val > 0 else 0
                print(f"[{elapsed:5.1f}s] {asset}: {d} {p}/{total} | delta={delta_state} price={price_state}")
                print(f"         ptb_locked={ptb_locked} ptb=${ptb_val:,.0f} coin=${coin_usd:,.0f} delta=${delta_usd:,.0f}")
                print(f"         tile={pnl_big}")

        if changed:
            print()

    print("=== FINAL SUMMARY ===")
    for asset in ['BTC', 'ETH']:
        ev = results.get(asset)
        if not ev:
            continue
        print(f"{asset}: decision={ev.decision.value}")
        for rr in ev.rule_results:
            val = rr.detail.get('live_value', '')
            print(f"  {rr.rule_name}: {rr.state.value} val={val}")

    await orch.stop()
    await close_db()
    print()
    print("Done.")

if __name__ == '__main__':
    asyncio.run(main())
