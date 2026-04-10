"""Debug: PTB locked ama evaluation goremiyor — neden?"""
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

    await orch.start()
    bal = await orch.clob_client.get_balance()
    if bal:
        orch.balance_manager.update(bal['available'], bal.get('total', bal['available']))
        orch.trading_enabled = True

    await asyncio.sleep(10)

    # PTB records
    print("=== PTB RECORDS ===")
    ptb_records = dict(orch.ptb_fetcher._records)
    ptb_cids = set(ptb_records.keys())
    for cid, rec in ptb_records.items():
        val = rec.ptb_value if rec.ptb_value else 0
        print(f"  PTB cid={cid[:24]}... asset={rec.asset} locked={rec.is_locked} val=${val:,.2f}")

    # Pipeline
    print()
    print("=== PIPELINE ===")
    btc_pipe = orch.pipeline.get_record_by_asset('BTC')
    if btc_pipe:
        print(f"  pipeline BTC: cid={btc_pipe.condition_id[:24]}...")
        print(f"  cid in PTB?: {btc_pipe.condition_id in ptb_cids}")
    else:
        print("  pipeline BTC: NONE (RTDS outcome price gelmiyor)")
        print("  -> evaluation condition_id bos string olacak")
        print("  -> ptb_fetcher.get_record('') = None")
        print("  -> PTB dolu olsa bile evaluation onu GOREMEZ")

    # Evaluation context simulation
    print()
    print("=== EVALUATION CONTEXT SIMULATION ===")
    # evaluation_loop._evaluate_single logic:
    # price_record = self._pipeline.get_record_by_asset(asset)
    # condition_id = price_record.condition_id if price_record else ""
    # ptb_record = self._ptb_fetcher.get_record(condition_id) if condition_id else None
    condition_id = btc_pipe.condition_id if btc_pipe else ""
    print(f"  condition_id from pipeline: '{condition_id[:24]}...' " if condition_id else f"  condition_id from pipeline: '' (EMPTY)")
    ptb_lookup = orch.ptb_fetcher.get_record(condition_id) if condition_id else None
    print(f"  ptb_fetcher.get_record(cid): {ptb_lookup}")

    # Workaround: PTB'yi asset ile ara
    print()
    print("=== ALTERNATIVE: PTB BY ASSET ===")
    for cid, rec in ptb_records.items():
        if rec.asset.upper() == 'BTC':
            print(f"  BTC PTB found by scanning: cid={cid[:24]}... val=${rec.ptb_value:,.2f}")

    await orch.stop()
    await close_db()

if __name__ == '__main__':
    asyncio.run(main())
