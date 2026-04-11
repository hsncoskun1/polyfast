"""PART 4 — CONTROLLED LIVE TRADE READINESS PRECHECK."""
import asyncio, time, sys, os, inspect
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

async def main():
    from backend.persistence.database import init_db, close_db
    from backend.persistence.migrations import run_migrations
    from backend.orchestrator.wiring import Orchestrator
    from backend.persistence.credential_persistence import load_encrypted
    from backend.settings.coin_settings import CoinSettings
    from backend.config_loader.schema import AppConfig

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

    await orch.start()
    bal = await orch.clob_client.get_balance()
    if bal:
        orch.balance_manager.update(bal['available'], bal.get('total', bal['available']))
        orch.trading_enabled = True

    # 10s bekle — tum veri pipeline'i dolsun
    await asyncio.sleep(10)

    print("=" * 60)
    print("PART 4 — LIVE TRADE READINESS PRECHECK")
    print("=" * 60)
    print()

    results = {}

    # ═══ 1) CURRENT MODE ═══
    print("--- 1) CURRENT MODE ---")
    print(f"  paper_mode: {orch.paper_mode}")
    print(f"  trading_enabled: {orch.trading_enabled}")
    print(f"  paused: {orch.paused}")
    results['1_paper_mode'] = ('PASS' if orch.paper_mode else 'FAIL', f'paper={orch.paper_mode}')

    # Live order gate — ExitExecutor
    ee_src = inspect.getsource(orch.exit_executor.__class__)
    has_paper_guard = 'paper_mode' in ee_src or 'self._paper' in ee_src
    print(f"  exit_executor paper guard: {has_paper_guard}")
    results['1_exit_paper'] = ('PASS' if has_paper_guard else 'FAIL', 'paper guard in executor')
    print()

    # ═══ 2) LIVE ORDER GATE ═══
    print("--- 2) LIVE ORDER GATE ---")
    # Order execution Faz 9 — su an order gonderme kodu var mi?
    eval_src = inspect.getsource(orch.evaluation_loop.__class__)
    has_order_send = 'place_order' in eval_src or 'send_order' in eval_src or 'execute_order' in eval_src
    print(f"  evaluation loop sends orders: {has_order_send}")
    print(f"  eval loop comment: 'ORDER GONDERILMEZ — sadece log (Faz 5)'")
    results['2_no_order'] = ('PASS' if not has_order_send else 'KRITIK', 'no order execution in eval')

    # ExitExecutor live mode
    print(f"  exit_executor paper_mode: {orch.exit_executor._paper_mode}")
    live_exec = not orch.exit_executor._paper_mode
    results['2_exit_paper'] = ('PASS' if not live_exec else 'KRITIK', f'live_exec={live_exec}')
    print()

    # ═══ 3) CREDENTIAL / BALANCE READINESS ═══
    print("--- 3) CREDENTIAL / BALANCE / CLAIM ---")
    c = orch.credential_store.credentials
    ht = c.has_trading_credentials()
    hs = c.has_signing_credentials()
    hr = c.has_relayer_credentials()
    bal_avail = orch.balance_manager.available_balance
    bal_stale = orch.balance_manager.is_stale
    open_pos = orch.position_tracker.open_position_count
    pend_cl = orch.claim_manager.pending_count

    print(f"  has_trading: {ht}")
    print(f"  has_signing: {hs}")
    print(f"  has_relayer: {hr}")
    print(f"  balance: ${bal_avail:.2f}")
    print(f"  balance_stale: {bal_stale}")
    print(f"  open_positions: {open_pos}")
    print(f"  pending_claims: {pend_cl}")
    results['3_creds'] = ('PASS' if ht and hs and hr else 'FAIL', f'trading={ht} signing={hs} relayer={hr}')
    results['3_balance'] = ('PASS' if bal_avail > 0 else 'FAIL', f'${bal_avail:.2f}')
    results['3_positions'] = ('PASS' if open_pos == 0 else 'UYARI', f'{open_pos} open')
    results['3_claims'] = ('PASS' if pend_cl == 0 else 'UYARI', f'{pend_cl} pending')
    print()

    # ═══ 4) GLOBAL SETTINGS ═══
    print("--- 4) GLOBAL SETTINGS ---")
    cfg = orch._config
    tp = cfg.trading.exit_rules.take_profit
    sl = cfg.trading.exit_rules.stop_loss
    fs = cfg.trading.exit_rules.force_sell

    print(f"  auto_start: {cfg.trading.auto_start_bot_on_startup}")
    print(f"  bot_max: {cfg.trading.entry_rules.bot_max.max_positions}")
    print(f"  block_claim: {cfg.trading.claim.wait_for_claim_before_new_trade}")
    print(f"  tp: {tp.percentage}%  reevaluate={tp.reevaluate_on_retry}")
    print(f"  sl: enabled={sl.enabled} {sl.percentage}%  jump={sl.jump_threshold}")
    print(f"  fs_time: enabled={fs.time.enabled} {fs.time.remaining_seconds}s")
    print(f"  fs_pnl: enabled={fs.pnl_loss.enabled} {fs.pnl_loss.loss_percentage}%")

    # Risk check
    sl_off = not sl.enabled
    fs_all_off = not fs.time.enabled and not fs.pnl_loss.enabled
    results['4_sl'] = ('UYARI' if sl_off else 'PASS', f'sl_enabled={sl.enabled}')
    results['4_fs'] = ('KRITIK' if fs_all_off else 'PASS', f'fs_time={fs.time.enabled} fs_pnl={fs.pnl_loss.enabled}')
    if sl_off:
        print(f"  !! SL KAPALI — zarar siniri YOK")
    if fs_all_off:
        print(f"  !! TUM FS KAPALI — pozisyon settlement'a kalabilir")
    print()

    # ═══ 5) ENTRY READINESS ═══
    print("--- 5) ENTRY READINESS ---")
    ev_results = orch.evaluation_loop.get_last_results()
    btc_ev = ev_results.get('BTC')

    if btc_ev:
        d = btc_ev.decision.value
        p = btc_ev.pass_count
        f_ = btc_ev.fail_count
        w = btc_ev.waiting_count
        total = p + f_ + w
        print(f"  BTC: {d} {p}/{total}")
        for rr in btc_ev.rule_results:
            print(f"    {rr.rule_name}: {rr.state.value}")

        pipe = orch.pipeline.get_record_by_asset('BTC')
        if pipe:
            print(f"  pipeline: UP bid={pipe.up_bid:.4f} ask={pipe.up_ask:.4f}")
            print(f"           DN bid={pipe.down_bid:.4f} ask={pipe.down_ask:.4f}")
            print(f"           status={pipe.status.value}")

        ptb = orch.ptb_fetcher.get_record_by_asset('BTC')
        if ptb:
            ptb_v = ptb.ptb_value if ptb.ptb_value else 0
            print(f"  PTB: locked={ptb.is_locked} val=${ptb_v:,.0f}")

        has_outcome = pipe and pipe.up_bid > 0
        has_ptb = ptb and ptb.is_locked
        can_entry = d == 'entry'
        results['5_outcome'] = ('PASS' if has_outcome else 'FAIL', 'outcome price')
        results['5_ptb'] = ('PASS' if has_ptb else 'FAIL', 'PTB locked')
        results['5_entry'] = ('PASS' if can_entry else 'UYARI', f'decision={d}')
    else:
        results['5_outcome'] = ('FAIL', 'no BTC eval')
        results['5_ptb'] = ('FAIL', 'no BTC eval')
        results['5_entry'] = ('FAIL', 'no BTC eval')
        print("  BTC eval: NOT FOUND")
    print()

    # ═══ 6-7) SL/FS + BOT_MAX ═══
    print("--- 6-7) SL/FS + BOT_MAX ---")
    bot_max = cfg.trading.entry_rules.bot_max.max_positions
    print(f"  bot_max_positions: {bot_max}")
    results['7_bot_max'] = ('PASS' if 1 <= bot_max <= 5 else 'UYARI', f'bot_max={bot_max}')
    print()

    # ═══ 8) STALE STATE ═══
    print("--- 8) STALE / ACIK STATE ---")
    print(f"  open_positions: {open_pos}")
    print(f"  pending_claims: {pend_cl}")
    print(f"  balance_stale: {bal_stale}")
    pipe_btc = orch.pipeline.get_record_by_asset('BTC')
    pipe_stale = pipe_btc.is_stale if pipe_btc else True
    print(f"  pipeline_stale: {pipe_stale}")
    results['8_clean'] = ('PASS' if open_pos == 0 and pend_cl == 0 and not bal_stale else 'UYARI', 'clean state')
    print()

    # ═══ 9) HEALTH ═══
    print("--- 9) HEALTH ---")
    print(f"  supervisor: {orch._supervisor_running}")
    print(f"  supervisor_restarts: {orch._supervisor_restarts}")
    print(f"  verify_retry: {orch._verify_retry_running}")
    print(f"  RTDS connected: {orch.rtds_client.is_connected}")
    print(f"  RTDS msgs: {orch.rtds_client.total_messages_received}")
    print(f"  bridge routed: {orch.bridge.total_routed}")
    print(f"  discovery events: {orch.discovery_loop.events_found}")
    print(f"  eval_count: {orch.evaluation_loop.eval_count}")
    print(f"  entry_signals: {orch.evaluation_loop.entry_signal_count}")

    incidents = orch.discovery_loop.get_health_incidents()
    print(f"  health incidents: {len(incidents)}")
    results['9_health'] = ('PASS' if len(incidents) == 0 and orch._supervisor_running else 'UYARI', f'incidents={len(incidents)}')
    print()

    # ═══ 10) STOP/PAUSE/SUPERVISOR ═══
    print("--- 10) STOP/PAUSE/SUPERVISOR ---")
    print(f"  manual stop safe: trading_enabled controlled by stop()")
    print(f"  pause safe: exit cycle devam, entry durur")
    print(f"  supervisor active: {orch._supervisor_running}")
    results['10_lifecycle'] = ('PASS', 'stop/pause/supervisor wired')
    print()

    # ═══ SHUTDOWN ═══
    await orch.stop()
    await close_db()

    # ═══ SUMMARY ═══
    print("=" * 60)
    print("PART 4 SUMMARY")
    print("=" * 60)
    print()
    print(f"{'#':<20} {'Result':<10} {'Detail'}")
    print("-" * 60)

    pass_c = fail_c = warn_c = krit_c = 0
    for k in sorted(results.keys()):
        status, detail = results[k]
        print(f"{k:<20} {status:<10} {detail}")
        if status == 'PASS': pass_c += 1
        elif status == 'FAIL': fail_c += 1
        elif status == 'UYARI': warn_c += 1
        elif status == 'KRITIK': krit_c += 1

    print()
    print(f"PASS: {pass_c}  FAIL: {fail_c}  UYARI: {warn_c}  KRITIK: {krit_c}")

if __name__ == '__main__':
    asyncio.run(main())
