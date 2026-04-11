"""v0.9.2 Controlled Live Test — BTC $1 FOK full cycle."""
import asyncio, time, sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Force flush
import functools
print = functools.partial(print, flush=True)

async def main():
    from backend.persistence.database import init_db, close_db
    from backend.persistence.migrations import run_migrations
    from backend.orchestrator.wiring import Orchestrator
    from backend.persistence.credential_persistence import load_encrypted
    from backend.settings.coin_settings import CoinSettings
    from backend.execution.clob_client_wrapper import LIVE_ORDER_ENABLED
    from backend.execution.order_executor import ExecutionMode

    db = await init_db()
    await run_migrations(db)

    orch = Orchestrator()
    creds = load_encrypted()
    orch.credential_store.load(creds)

    # Sadece BTC — tek coin, tek pozisyon
    # Dominant taraftan giris: price_min=51 (dominant her zaman >=50)
    orch.settings_store.set(CoinSettings(
        coin='BTC', coin_enabled=True,
        delta_threshold=0.00001, price_min=51, price_max=99,
        time_min=10, time_max=290, order_amount=1.0, event_max=1,
    ))
    # ETH disable — sadece BTC
    orch.settings_store.set(CoinSettings(coin='ETH', coin_enabled=False))
    # bot_max=1
    orch._config.trading.entry_rules.bot_max.max_positions = 1
    orch.order_executor._bot_max = 1

    await orch.start()
    bal = await orch.clob_client.get_balance()
    if bal:
        orch.balance_manager.update(bal['available'], bal.get('total', bal['available']))
        orch.trading_enabled = True
    # Periyodik balance refresh baslat
    await orch.balance_manager.start_passive_refresh()

    print("=" * 60)
    print("v0.9.2 CONTROLLED LIVE TEST")
    print("=" * 60)
    print()

    # Pre-check
    print("--- PRE-CHECK ---")
    print(f"  LIVE_ORDER_ENABLED: {LIVE_ORDER_ENABLED}")
    print(f"  paper_mode: {orch.paper_mode}")
    print(f"  order_executor mode: {orch.order_executor.mode.value}")
    print(f"  signature_type: {orch._config.trading.signature_type}")
    print(f"  bot_max: {orch.order_executor._bot_max}")
    print(f"  balance: ${orch.balance_manager.available_balance:.2f}")
    print(f"  funder: {creds.funder_address[:8]}****{creds.funder_address[-4:]}")
    print()

    # Bekle — veri pipeline dolsun
    print("--- PIPELINE BEKLEME (15s) ---")
    entry_seen = False
    buy_result = None
    position_id = None
    fill_price = 0
    entry_time = 0

    for i in range(30):  # max 75s
        await asyncio.sleep(2.5)
        elapsed = (i + 1) * 2.5

        results = orch.evaluation_loop.get_last_results()
        btc_ev = results.get('BTC')
        if not btc_ev:
            if elapsed <= 15 and i % 4 == 0:
                print(f"  [{elapsed:.0f}s] BTC eval bekleniyor...")
            continue

        d = btc_ev.decision.value
        p = btc_ev.pass_count
        total = p + btc_ev.fail_count + btc_ev.waiting_count

        # Pozisyon durumu
        open_pos = orch.position_tracker.open_position_count
        exec_count = orch.order_executor.execution_count
        fill_count = orch.order_executor.fill_count

        if d == 'entry' and not entry_seen:
            entry_seen = True
            entry_time = elapsed
            print(f"  [{elapsed:.0f}s] ENTRY SIGNAL! {p}/{total}")
            print(f"    exec_count={exec_count} fill_count={fill_count} open={open_pos}")

        if fill_count > 0 and buy_result is None:
            buy_result = True
            print(f"  [{elapsed:.0f}s] FILL DETECTED!")
            print(f"    exec={exec_count} fills={fill_count} open={open_pos}")
            # Pozisyon bilgisi
            for pos in orch.position_tracker.get_all_positions():
                if pos.is_open:
                    position_id = pos.position_id
                    fill_price = pos.fill_price
                    print(f"    pos={pos.position_id[:12]}...")
                    print(f"    asset={pos.asset} side={pos.side}")
                    print(f"    fill_price={pos.fill_price:.4f}")
                    print(f"    net_shares={pos.net_position_shares:.4f}")
                    print(f"    fee_rate={pos.fee_rate}")
                    print(f"    requested_usd={pos.requested_amount_usd}")

        if open_pos > 0 and i % 4 == 0:
            # Exit izleme
            for pos in orch.position_tracker.get_all_positions():
                if pos.is_open:
                    pipe = orch.pipeline.get_record_by_asset('BTC')
                    if pipe:
                        held_bid = pipe.up_bid if pos.side == 'UP' else pipe.down_bid
                        pnl_info = pos.calculate_unrealized_pnl(held_bid)
                        pnl_pct = pnl_info.get('net_unrealized_pnl_pct', 0)
                        print(f"  [{elapsed:.0f}s] OPEN: price={held_bid:.4f} pnl={pnl_pct:.2f}% state={pos.state.value}")

        # Pozisyon kapandi mi
        closed_count = sum(1 for pos in orch.position_tracker.get_all_positions() if pos.is_closed and pos.net_realized_pnl is not None)
        if closed_count > 0 and buy_result:
            for pos in orch.position_tracker.get_all_positions():
                if pos.is_closed and pos.net_realized_pnl is not None:
                    print(f"  [{elapsed:.0f}s] CLOSED!")
                    print(f"    reason={pos.close_reason.value if pos.close_reason else '?'}")
                    print(f"    exit_price={pos.exit_fill_price:.4f}")
                    print(f"    net_pnl=${pos.net_realized_pnl:.4f}")
                    print(f"    entry=${pos.requested_amount_usd:.2f} exit=${pos.net_exit_usdc:.4f}")
            break

        # Zaman kontrolu — 75s'de dur
        if elapsed >= 75:
            print(f"  [{elapsed:.0f}s] TIMEOUT — test suresi doldu")
            break

    # Final rapor
    print()
    print("=" * 60)
    print("v0.9.2 TEST RAPORU")
    print("=" * 60)
    print()

    # Balance
    try:
        bal2 = await orch.clob_client.get_balance()
        if bal2:
            new_bal = bal2['available']
        else:
            new_bal = orch.balance_manager.available_balance
    except:
        new_bal = orch.balance_manager.available_balance

    print(f"Balance oncesi: ${orch.balance_manager.available_balance:.2f}")
    print(f"Balance sonrasi: ${new_bal:.2f}")
    print()

    # Executor stats
    print(f"Order executor:")
    print(f"  execution_count: {orch.order_executor.execution_count}")
    print(f"  fill_count: {orch.order_executor.fill_count}")
    print(f"  reject_count: {orch.order_executor._reject_count}")
    print()

    # Exit stats
    print(f"Exit executor:")
    print(f"  close_count: {orch.exit_executor.close_count}")
    print(f"  retry_count: {orch.exit_executor.retry_count}")
    print()

    # Pozisyonlar
    all_pos = orch.position_tracker.get_all_positions()
    print(f"Pozisyonlar: {len(all_pos)}")
    for pos in all_pos:
        print(f"  {pos.position_id[:12]}... {pos.asset} {pos.side}")
        print(f"    state={pos.state.value}")
        print(f"    fill_price={pos.fill_price:.4f}")
        print(f"    net_shares={pos.net_position_shares:.4f}")
        if pos.is_closed:
            print(f"    exit_price={pos.exit_fill_price:.4f}")
            print(f"    net_pnl=${pos.net_realized_pnl:.4f}")
            print(f"    close_reason={pos.close_reason.value if pos.close_reason else '?'}")
    print()

    # Health
    print(f"Health:")
    print(f"  supervisor: {orch._supervisor_running}")
    print(f"  RTDS: {orch.rtds_client.is_connected}")
    print(f"  entry_signals: {orch.evaluation_loop.entry_signal_count}")
    print(f"  eval_count: {orch.evaluation_loop.eval_count}")

    await orch.stop()
    await close_db()
    print()
    print("TEST TAMAMLANDI")

if __name__ == '__main__':
    asyncio.run(main())
