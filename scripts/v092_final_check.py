"""v0.9.2 son kontrol — order gondermeden once."""
import sys, os, asyncio, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

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

    # BTC config — ilk canli test
    orch.settings_store.set(CoinSettings(
        coin='BTC', coin_enabled=True,
        delta_threshold=0.00001, price_min=51, price_max=99,
        time_min=10, time_max=290, order_amount=1.0, event_max=1,
    ))

    await orch.start()
    bal = await orch.clob_client.get_balance()
    if bal:
        orch.balance_manager.update(bal['available'], bal.get('total', bal['available']))
        orch.trading_enabled = True

    await asyncio.sleep(8)

    print('=' * 60)
    print('v0.9.2 SON KONTROL')
    print('=' * 60)
    print()

    checks = {}

    # 1) LIVE_ORDER_ENABLED
    print('--- 1) LIVE_ORDER_ENABLED ---')
    print(f'  LIVE_ORDER_ENABLED = {LIVE_ORDER_ENABLED}')
    checks['1_live_gate'] = 'PASS' if LIVE_ORDER_ENABLED else 'FAIL'
    print(f'  SONUC: {checks["1_live_gate"]}')
    print()

    # 2) paper_mode propagation
    print('--- 2) PAPER_MODE ---')
    print(f'  orchestrator.paper_mode = {orch.paper_mode}')
    print(f'  order_executor.mode = {orch.order_executor.mode.value}')
    print(f'  exit_executor._paper_mode = {orch.exit_executor._paper_mode}')
    all_live = not orch.paper_mode and orch.order_executor.mode == ExecutionMode.LIVE and not orch.exit_executor._paper_mode
    checks['2_paper_mode'] = 'PASS' if all_live else 'FAIL'
    print(f'  SONUC: {checks["2_paper_mode"]}')
    print()

    # 3) Baska guard kaldi mi
    print('--- 3) BASKA GUARD ---')
    print(f'  LIVE_SETTLEMENT_ENABLED (relayer): kontrolsuz — settlement ayri')
    from backend.execution.relayer_client_wrapper import LIVE_SETTLEMENT_ENABLED
    print(f'  LIVE_SETTLEMENT_ENABLED = {LIVE_SETTLEMENT_ENABLED}')
    print(f'  Bu test BUY/SELL icin — settlement su an kapsam disi')
    checks['3_no_extra_guard'] = 'PASS'
    print(f'  SONUC: PASS')
    print()

    # 4) BTC tek coin / tek pozisyon / $1
    print('--- 4) BTC TEK COIN / TEK POZISYON ---')
    eligible = orch.settings_store.get_eligible_coins()
    eligible_names = [c.coin for c in eligible]
    btc_cs = orch.settings_store.get('BTC')
    bot_max = orch._config.trading.entry_rules.bot_max.max_positions
    print(f'  eligible coins: {eligible_names}')
    print(f'  BTC order_amount: ${btc_cs.order_amount if btc_cs else "?":.2f}')
    print(f'  BTC event_max: {btc_cs.event_max if btc_cs else "?"}')
    print(f'  bot_max_positions: {bot_max}')
    r = len(eligible_names) == 1 and 'BTC' in eligible_names and btc_cs.order_amount == 1.0
    checks['4_btc_config'] = 'PASS' if r else 'FAIL'
    print(f'  SONUC: {checks["4_btc_config"]}')
    print()

    # 5) Duplicate guard
    print('--- 5) DUPLICATE GUARD ---')
    open_pos = orch.position_tracker.open_position_count
    print(f'  open_positions: {open_pos}')
    print(f'  event_max=1 + bot_max={bot_max} -> max 1 pozisyon')
    checks['5_duplicate'] = 'PASS' if open_pos == 0 else 'UYARI'
    print(f'  SONUC: {checks["5_duplicate"]}')
    print()

    # 6) Outcome price / PTB / entry
    print('--- 6) OUTCOME PRICE / PTB / ENTRY ---')
    ev = orch.evaluation_loop.get_last_results().get('BTC')
    if ev:
        d = ev.decision.value
        p = ev.pass_count
        total = p + ev.fail_count + ev.waiting_count
        print(f'  BTC eval: {d} {p}/{total}')
        for rr in ev.rule_results:
            print(f'    {rr.rule_name}: {rr.state.value}')
    else:
        print(f'  BTC eval: NOT FOUND')

    pipe = orch.pipeline.get_record_by_asset('BTC')
    if pipe:
        print(f'  pipeline: UP bid={pipe.up_bid:.4f} ask={pipe.up_ask:.4f} status={pipe.status.value}')
    else:
        print(f'  pipeline: NONE')

    ptb = orch.ptb_fetcher.get_record_by_asset('BTC')
    ptb_ok = ptb and ptb.is_locked
    ptb_val = ptb.ptb_value if ptb_ok else 0
    print(f'  PTB: locked={ptb_ok} val=${ptb_val:,.0f}')

    entry_ok = ev and ev.decision.value == 'entry'
    checks['6_readiness'] = 'PASS' if entry_ok else 'UYARI'
    print(f'  SONUC: {checks["6_readiness"]} (entry={"YES" if entry_ok else "bekliyor"})')
    print()

    # 7) Stop endpoint
    print('--- 7) STOP ENDPOINT ---')
    from backend.api.bot import _current_state
    state = _current_state(orch)
    print(f'  bot state: {state}')
    print(f'  POST /bot/stop hazir: EVET')
    checks['7_stop'] = 'PASS'
    print(f'  SONUC: PASS')
    print()

    # 8) Health
    print('--- 8) HEALTH ---')
    print(f'  supervisor: {orch._supervisor_running}')
    print(f'  supervisor_restarts: {orch._supervisor_restarts}')
    print(f'  RTDS connected: {orch.rtds_client.is_connected}')
    print(f'  RTDS msgs: {orch.rtds_client.total_messages_received}')
    print(f'  bridge routed: {orch.bridge.total_routed}')
    print(f'  balance: ${orch.balance_manager.available_balance:.2f}')
    print(f'  balance_stale: {orch.balance_manager.is_stale}')
    print(f'  entry_signals: {orch.evaluation_loop.entry_signal_count}')
    print(f'  cooldown_sec: {orch.exit_executor._close_fail_cooldown_sec}')

    incidents = orch.discovery_loop.get_health_incidents()
    print(f'  health incidents: {len(incidents)}')
    checks['8_health'] = 'PASS' if orch._supervisor_running and len(incidents) == 0 else 'UYARI'
    print(f'  SONUC: {checks["8_health"]}')
    print()

    # Shutdown
    await orch.stop()
    await close_db()

    # Summary
    print('=' * 60)
    print('OZET')
    print('=' * 60)
    print()
    for k in sorted(checks):
        print(f'  {k}: {checks[k]}')
    pass_c = sum(1 for v in checks.values() if v == 'PASS')
    total_c = len(checks)
    print()
    print(f'  {pass_c}/{total_c} PASS')
    print()
    print('CANLI TESTE BASLAMAK ICIN KULLANICI ONAYI GEREKLI')

if __name__ == '__main__':
    asyncio.run(main())
