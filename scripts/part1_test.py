"""PART 1 — STARTUP / RESTORE / READINESS live test."""

import asyncio
import time
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


async def part1():
    print('=' * 60)
    print('PART 1 — STARTUP / RESTORE / READINESS')
    print('=' * 60)
    print()

    # DB init
    from backend.persistence.database import init_db, close_db
    from backend.persistence.migrations import run_migrations
    db = await init_db()
    applied = await run_migrations(db)
    print(f'[DB] migrations applied: {applied}')

    from backend.orchestrator.wiring import Orchestrator
    from backend.persistence.credential_persistence import load_encrypted, has_encrypted_file

    orch = Orchestrator()

    # ═══ A) CREDENTIAL RESTORE ═══
    print()
    print('--- A) CREDENTIAL RESTORE ---')

    enc_exists = has_encrypted_file()
    print(f'  A1 encrypted file exists: {enc_exists}')

    credential_ok = False
    can_place = False
    can_claim = False
    missing = []

    if enc_exists:
        try:
            creds = load_encrypted()
            if creds and creds.private_key:
                orch.credential_store.load(creds)
                credential_ok = True
                ht = creds.has_trading_credentials()
                hs = creds.has_signing_credentials()
                hr = creds.has_relayer_credentials()
                print(f'  A2 decrypt+load: OK')
                print(f'  A3 has_trading={ht} has_signing={hs} has_relayer={hr}')
                print(f'  A4 funder: {creds.funder_address[:6]}****{creds.funder_address[-4:]}')
                can_place = ht and hs
                can_claim = can_place and hr
                if not creds.private_key: missing.append('private_key')
                if not creds.relayer_key: missing.append('relayer_key')
            else:
                print(f'  A2 decrypt OK but pk empty')
        except Exception as e:
            print(f'  A2 decrypt FAILED: {type(e).__name__}')
    else:
        print(f'  A2 NO encrypted file')

    # ═══ B) BALANCE ═══
    print()
    print('--- B) BALANCE ---')

    balance_ok = False
    bal_amount = 0.0
    try:
        bal = await orch.clob_client.get_balance()
        if bal:
            bal_amount = bal['available']
            orch.balance_manager.update(bal_amount, bal.get('total', bal_amount))
            balance_ok = True
            print(f'  B1 fetch: OK')
            print(f'  B2 available: ${bal_amount:.2f}')
            print(f'  B3 is_stale: {orch.balance_manager.is_stale}')
        else:
            print(f'  B1 fetch returned None')
    except Exception as e:
        print(f'  B1 fetch FAILED: {type(e).__name__}')

    # is_fully_ready
    is_ready = can_place and can_claim and balance_ok and len(missing) == 0
    print(f'  B4 is_fully_ready: {is_ready}')
    modal_should_open = not is_ready
    print(f'  B5 credential modal should open: {modal_should_open}')

    # ═══ C) BOT STATE ═══
    print()
    print('--- C) BOT STATE ---')

    auto_start = orch._config.trading.auto_start_bot_on_startup
    print(f'  C1 auto_start_bot_on_startup: {auto_start}')

    # StartupGuard sim
    if credential_ok and balance_ok:
        orch.trading_enabled = True
        guard = 'NORMAL'
    elif credential_ok and not balance_ok:
        guard = 'DEGRADED'
    else:
        guard = 'WAITING'
    print(f'  C2 StartupGuard: {guard}')
    print(f'  C3 trading_enabled: {orch.trading_enabled}')
    print(f'  C4 paper_mode: {orch.paper_mode}')
    print(f'  C5 paused: {orch.paused}')

    expected_bot = 'stopped' if not orch.trading_enabled else ('paused' if orch.paused else 'running')
    if auto_start and credential_ok and balance_ok:
        expected_bot = 'running'
    elif not auto_start:
        # auto_start false ama loops yine de basliyor (koşulsuz)
        # trading_enabled True ise state = running
        pass
    print(f'  C6 expected bot state: {expected_bot}')

    # ═══ D) DASHBOARD / RESTORE ═══
    print()
    print('--- D) DASHBOARD / RESTORE ---')

    await orch.start()

    settings_all = orch.settings_store.get_all()
    eligible = orch.settings_store.get_eligible_coins()
    open_pos = orch.position_tracker.open_position_count
    pending_cl = orch.claim_manager.pending_count
    print(f'  D1 settings restored: {len(settings_all)} coins')
    for cs in settings_all:
        print(f'      {cs.coin}: enabled={cs.coin_enabled} configured={cs.is_configured} eligible={cs.is_trade_eligible}')
    print(f'  D2 eligible: {len(eligible)}')
    print(f'  D3 open_positions: {open_pos}')
    print(f'  D4 pending_claims: {pending_cl}')

    # Wait for discovery + eval
    await asyncio.sleep(5)

    search_tiles = orch.build_search_snapshot()
    idle_tiles = orch.build_idle_snapshot()
    print(f'  D5 search tiles: {len(search_tiles)}')
    for t in search_tiles[:5]:
        coin = t.get('coin', '?')
        pnl_big = t.get('pnl_big', '?')
        rules = t.get('rules', [])
        spread_r = next((r for r in rules if 'spread' in r.get('label', '').lower()), None)
        spread_state = spread_r['state'] if spread_r else 'N/A'
        print(f'      {coin}: {pnl_big} spread={spread_state}')
    print(f'  D6 idle tiles: {len(idle_tiles)}')
    for t in idle_tiles[:5]:
        coin = t.get('coin') or 'GLOBAL'
        kind = t.get('idle_kind', '?')
        msg = (t.get('msg') or '')[:50]
        print(f'      {coin}: {kind} — {msg}')
    print(f'  D7 gereksiz modal: {modal_should_open}')

    # ═══ E) LOG / HEALTH ═══
    print()
    print('--- E) LOG / HEALTH ---')

    print(f'  E1 supervisor_running: {orch._supervisor_running}')
    print(f'  E2 supervisor_restarts: {orch._supervisor_restarts}')
    print(f'  E3 verify_retry_running: {orch._verify_retry_running}')
    print(f'  E4 discovery.is_running: {orch.discovery_loop.is_running}')
    print(f'  E5 evaluation.is_running: {orch.evaluation_loop.is_running}')
    print(f'  E6 exit_cycle_running: {orch._exit_cycle_running}')
    print(f'  E7 coin_client._running: {orch.coin_client._running}')

    incidents = orch.discovery_loop.get_health_incidents()
    print(f'  E8 health incidents: {len(incidents)}')
    for inc in incidents[:3]:
        print(f'      {inc.severity.value}: {inc.message[:80]}')

    print(f'  E9 discovery events: {orch.discovery_loop.events_found}')
    print(f'  E10 discovery scans: {orch.discovery_loop.scan_count}')
    print(f'  E11 eval_count: {orch.evaluation_loop.eval_count}')
    print(f'  E12 entry_signals: {orch.evaluation_loop.entry_signal_count}')

    # Coin price check
    for coin in ['BTC', 'ETH']:
        rec = orch.coin_client.get_price(coin)
        p = rec.usd_price if rec else 0
        print(f'  E13 {coin} USD: ${p:,.2f}')

    # Shutdown
    print()
    await orch.stop()
    await close_db()
    print('Graceful shutdown OK')
    print()
    print('=' * 60)
    print('PART 1 COMPLETE')
    print('=' * 60)


if __name__ == '__main__':
    asyncio.run(part1())
