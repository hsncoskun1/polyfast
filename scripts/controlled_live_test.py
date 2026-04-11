"""Controlled Live Test — BTC $1 FOK tek pozisyon, tek order denemesi."""
import asyncio
import time
import sys
import os
import functools

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
print = functools.partial(print, flush=True)

POLYMARKET_ADDR = '0xd019B11c6572eCDb8F0036787f853Ef1A7EC2535'


async def main():
    from backend.persistence.database import init_db, close_db
    from backend.persistence.migrations import run_migrations
    from backend.orchestrator.wiring import Orchestrator
    from backend.persistence.credential_persistence import load_encrypted
    from backend.settings.coin_settings import CoinSettings
    from backend.execution.clob_client_wrapper import LIVE_ORDER_ENABLED

    db = await init_db()
    await run_migrations(db)

    orch = Orchestrator()
    creds = load_encrypted()
    orch.credential_store.load(creds)

    # ── CONFIG ──
    orch.settings_store.set(CoinSettings(
        coin='BTC', coin_enabled=True,
        delta_threshold=0.00001, price_min=51, price_max=99,
        time_min=10, time_max=290, order_amount=1.0, event_max=1,
    ))
    orch.settings_store.set(CoinSettings(coin='ETH', coin_enabled=False))
    orch._config.trading.entry_rules.bot_max.max_positions = 1
    orch.order_executor._bot_max = 1

    await orch.start()

    # Balance fetch
    bal_before = 0.0
    bal_data = await orch.clob_client.get_balance()
    if bal_data:
        bal_before = bal_data['available']
        orch.balance_manager.update(bal_before, bal_data.get('total', bal_before))
        orch.trading_enabled = True
    await orch.balance_manager.start_passive_refresh()

    print("=" * 60)
    print("CONTROLLED LIVE TEST — BTC $1 FOK")
    print("=" * 60)
    print()
    print(f"LIVE_ORDER_ENABLED: {LIVE_ORDER_ENABLED}")
    print(f"paper_mode: {orch.paper_mode}")
    print(f"dispatch_enabled: {orch.evaluation_loop.is_order_dispatch_enabled}")
    print(f"balance: ${bal_before:.2f}")
    print(f"bot_max: {orch.order_executor._bot_max}")
    print()

    if bal_before < 1.0:
        print("HATA: Balance < $1.00 — test yapilamaz")
        await orch.stop()
        await close_db()
        return

    # ── CURRENT SLOT BEKLEME ──
    import re as _re
    now = int(time.time())
    slot_start = (now // 300) * 300
    slot_end = slot_start + 300
    wait_for_slot = slot_end - now
    print(f"--- CURRENT SLOT BEKLEME ---")
    print(f"  slot: {slot_start}-{slot_end}, kalan: {wait_for_slot}s")

    # Eger slot'un ilk 30s'inde degilsek sonraki slot'u bekle
    # (time_min=10 oldugu icin slot sonuna yakin girisebiliriz)
    # Ama en iyisi slot basinda baslamak
    # Slot'un en az 60s'i kaldiysa devam, yoksa sonraki slot bekle
    if wait_for_slot > 60:
        print(f"  Slot aktif ({wait_for_slot}s kaldi) — devam")
    else:
        wait_next = wait_for_slot + 5
        print(f"  Slot sonuna yakin — sonraki slot icin {wait_next:.0f}s bekleniyor...")
        await asyncio.sleep(max(0, wait_next))
        print(f"  Yeni slot basladi")

    # ── PIPELINE + CURRENT EVENT BEKLEME ──
    print("--- PIPELINE BEKLEME (max 45s) ---")
    entry_ready = False
    for i in range(90):
        await asyncio.sleep(0.5)
        elapsed = (i+1) * 0.5

        ev = orch.evaluation_loop.get_last_results().get('BTC')
        if not ev:
            if i % 10 == 0:
                print(f"  [{elapsed:.0f}s] BTC eval bekleniyor...")
            continue

        # Current slot kontrolu — evaluation_loop helper kullan
        current_cid = orch.evaluation_loop._find_current_slot_condition_id('BTC')
        is_current_event = False
        if current_cid:
            pipe = orch.pipeline.get_record(current_cid)
            is_current_event = pipe is not None and pipe.up_bid > 0

        if ev.decision.value == 'entry' and is_current_event:
            p = ev.pass_count
            t = p + ev.fail_count + ev.waiting_count
            print(f"  [{elapsed:.0f}s] BTC ENTRY {p}/{t} — CURRENT SLOT + pipeline hazir")
            entry_ready = True
            break

        if i % 10 == 0:
            d = ev.decision.value
            p = ev.pass_count
            t = p + ev.fail_count + ev.waiting_count
            cur = "CURRENT" if is_current_event else "UPCOMING"
            print(f"  [{elapsed:.0f}s] BTC {d} {p}/{t} [{cur}]")

    if not entry_ready:
        print("  TIMEOUT — current slot'ta entry sinyali gelmedi")
        await orch.stop()
        await close_db()
        return

    # ── DISPATCH ENABLE — TEK ORDER ──
    print()
    print("--- DISPATCH ENABLE ---")
    t_enable = time.time()
    orch.enable_trading()
    print(f"  dispatch ON — ilk ENTRY'de order gidecek")

    # ── ORDER BEKLEME ──
    buy_matched = False
    buy_rejected = False
    position_id = None
    fill_price = 0.0
    fee_rate = 0.0
    net_shares = 0.0
    buy_detail = {}
    t_fill = 0.0

    for i in range(20):  # max 10s
        await asyncio.sleep(0.5)
        elapsed = time.time() - t_enable

        exec_count = orch.order_executor.execution_count
        fill_count = orch.order_executor.fill_count
        reject_count = orch.order_executor._reject_count
        open_pos = orch.position_tracker.open_position_count

        # Guvenlk: open_position_count > 1 HEMEN DUR
        if open_pos > 1:
            print(f"  !!! HEMEN DUR: open_positions={open_pos} > 1 !!!")
            orch.disable_trading()
            break

        if fill_count > 0 and not buy_matched:
            buy_matched = True
            t_fill = time.time()
            orch.disable_trading()  # HEMEN OFF — ikinci order engelle
            print(f"  [{elapsed:.1f}s] BUY MATCHED! dispatch OFF")
            for pos in orch.position_tracker.get_all_positions():
                if pos.is_open:
                    position_id = pos.position_id
                    fill_price = pos.fill_price
                    fee_rate = pos.fee_rate
                    net_shares = pos.net_position_shares
                    print(f"    pos={pos.position_id[:12]}...")
                    print(f"    side={pos.side} fill={fill_price:.4f}")
                    print(f"    net_shares={net_shares:.4f} fee={fee_rate}")
                    print(f"    requested=${pos.requested_amount_usd}")
            break

        if exec_count > 0 and fill_count == 0 and reject_count > 0 and not buy_rejected:
            buy_rejected = True
            orch.disable_trading()  # OFF
            print(f"  [{elapsed:.1f}s] BUY REJECTED/NOT_MATCHED — dispatch OFF")
            print(f"    exec={exec_count} fill={fill_count} reject={reject_count}")
            break

        if i % 4 == 0:
            print(f"  [{elapsed:.1f}s] exec={exec_count} fill={fill_count} reject={reject_count} open={open_pos}")

    if not buy_matched and not buy_rejected:
        orch.disable_trading()
        print("  ORDER TIMEOUT — 10s icerisinde order gitmedi")

    # ── EXIT IZLEME (sadece fill olduysa) ──
    close_reason = None
    exit_price = 0.0
    net_pnl = 0.0
    net_exit_usdc = 0.0
    t_close = 0.0

    if buy_matched and position_id:
        print()
        print("--- EXIT IZLEME (max 60s) ---")

        for i in range(120):  # max 60s
            await asyncio.sleep(0.5)
            elapsed = time.time() - t_fill

            pos = None
            for p in orch.position_tracker.get_all_positions():
                if p.position_id == position_id:
                    pos = p
                    break

            if pos is None:
                print(f"  [{elapsed:.1f}s] POZISYON KAYBOLDU!")
                break

            if pos.is_closed:
                t_close = time.time()
                close_reason = pos.close_reason.value if pos.close_reason else "?"
                exit_price = pos.exit_fill_price or 0
                net_pnl = pos.net_realized_pnl or 0
                net_exit_usdc = pos.net_exit_usdc or 0
                print(f"  [{elapsed:.1f}s] CLOSED!")
                print(f"    reason={close_reason}")
                print(f"    exit_price={exit_price:.4f}")
                print(f"    net_pnl=${net_pnl:.4f}")
                print(f"    net_exit_usdc=${net_exit_usdc:.4f}")
                break

            if i % 8 == 0:
                pipe = orch.pipeline.get_record_by_asset('BTC')
                if pipe and pos.is_open:
                    held_bid = pipe.up_bid if pos.side == 'UP' else pipe.down_bid
                    pnl_info = pos.calculate_unrealized_pnl(held_bid)
                    pnl_pct = pnl_info.get('net_unrealized_pnl_pct', 0)
                    state = pos.state.value
                    print(f"  [{elapsed:.1f}s] {state} price={held_bid:.4f} pnl={pnl_pct:.1f}%")

            # 60s hemen dur
            if elapsed >= 60:
                print(f"  [{elapsed:.1f}s] EXIT TIMEOUT — 60s gecti, pozisyon hala acik!")
                break

    # ── BALANCE SONRASI ──
    await asyncio.sleep(2)
    bal_after = bal_before
    try:
        bal_data2 = await orch.clob_client.get_balance()
        if bal_data2:
            bal_after = bal_data2['available']
    except Exception:
        pass

    # ── RAPOR ──
    print()
    print("=" * 60)
    print("CONTROLLED LIVE TEST RAPORU")
    print("=" * 60)
    print()

    # 1) TEST SONUCU
    if buy_matched and close_reason:
        test_result = "BASARILI — full cycle tamamlandi"
    elif buy_matched and not close_reason:
        test_result = "KISMI — fill oldu ama exit tamamlanmadi"
    elif buy_rejected:
        test_result = "REJECTED — order kabul edilmedi"
    else:
        test_result = "BASARISIZ — order gitmedi veya timeout"
    print(f"1) TEST SONUCU: {test_result}")
    print()

    # 2) ORDER DETAY
    print(f"2) ORDER DETAY:")
    print(f"   BUY matched: {buy_matched}")
    print(f"   BUY rejected: {buy_rejected}")
    print(f"   executor: exec={orch.order_executor.execution_count} fill={orch.order_executor.fill_count} reject={orch.order_executor._reject_count}")
    if buy_matched:
        print(f"   fill_price: {fill_price:.4f}")
        print(f"   fee_rate: {fee_rate}")
        print(f"   net_shares: {net_shares:.4f}")
    print()

    # 3) POZISYON LIFECYCLE
    print(f"3) POZISYON LIFECYCLE:")
    if position_id:
        for pos in orch.position_tracker.get_all_positions():
            if pos.position_id == position_id:
                print(f"   id: {pos.position_id[:16]}...")
                print(f"   asset: {pos.asset} side: {pos.side}")
                print(f"   state: {pos.state.value}")
                print(f"   fill_price: {pos.fill_price:.4f}")
                if pos.is_closed:
                    print(f"   exit_price: {pos.exit_fill_price:.4f}")
                    print(f"   close_reason: {pos.close_reason.value if pos.close_reason else '?'}")
    else:
        print(f"   pozisyon olusturulmadi")
    print()

    # 4) FEE ACCOUNTING
    print(f"4) FEE ACCOUNTING:")
    if position_id:
        for pos in orch.position_tracker.get_all_positions():
            if pos.position_id == position_id:
                print(f"   entry_fee_shares: {pos.entry_fee_shares:.6f}")
                print(f"   gross_shares: {pos.gross_fill_shares:.6f}")
                print(f"   net_shares: {pos.net_position_shares:.6f}")
                if pos.is_closed:
                    print(f"   exit_gross_usdc: {pos.exit_gross_usdc:.6f}")
                    print(f"   exit_fee_usdc: {pos.actual_exit_fee_usdc:.6f}")
                    print(f"   net_exit_usdc: {pos.net_exit_usdc:.6f}")
                    print(f"   net_realized_pnl: ${pos.net_realized_pnl:.4f}")
    print()

    # 5) BALANCE
    print(f"5) BALANCE:")
    print(f"   oncesi: ${bal_before:.2f}")
    print(f"   sonrasi: ${bal_after:.2f}")
    print(f"   fark: ${bal_after - bal_before:.2f}")
    print()

    # 6) TIMING
    print(f"6) TIMING:")
    if t_fill > 0:
        print(f"   enable -> fill: {t_fill - t_enable:.1f}s")
    if t_close > 0 and t_fill > 0:
        print(f"   fill -> close: {t_close - t_fill:.1f}s")
    if t_close > 0:
        print(f"   enable -> close: {t_close - t_enable:.1f}s")
    print()

    # 7) SORUNLAR
    print(f"7) SORUNLAR:")
    issues = []
    if orch.position_tracker.open_position_count > 0:
        issues.append("ACIK POZISYON KALDI!")
    if orch._supervisor_restarts:
        issues.append(f"supervisor_restarts: {orch._supervisor_restarts}")
    if orch.exit_executor.retry_count > 0:
        issues.append(f"exit_retry_count: {orch.exit_executor.retry_count}")
    if not issues:
        print(f"   YOK")
    else:
        for iss in issues:
            print(f"   - {iss}")
    print()

    # 8) SONRAKI ADIM
    print(f"8) SONRAKI ADIM:")
    if test_result.startswith("BASARILI"):
        print(f"   Full cycle dogru calisti. Daha fazla test veya frontend'e gecis.")
    elif test_result.startswith("KISMI"):
        print(f"   Exit akisini incele — neden kapanmadi?")
    elif test_result.startswith("REJECTED"):
        print(f"   Reject nedenini incele — balance/duplicate/validator?")
    else:
        print(f"   Dispatch/evaluation/pipeline akisini incele")

    await orch.stop()
    await close_db()
    print()
    print("TEST TAMAMLANDI")


if __name__ == '__main__':
    asyncio.run(main())
