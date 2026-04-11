"""env2.txt'den credential oku, derive et, encrypt et, test et."""
import os, sys, asyncio, re, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

async def main():
    # 1. env2.txt oku
    path = os.path.join(os.path.expanduser('~'), 'OneDrive', 'Masaüstü', 'env2.txt')
    pk = ''
    metamask_addr = ''
    relayer = ''
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if ':' in line:
                key, _, val = line.partition(':')
            elif '=' in line:
                key, _, val = line.partition('=')
            else:
                continue
            key = key.strip().lower()
            val = val.strip()
            if 'private' in key:
                pk = val
            elif 'metamask' in key or 'address' in key:
                metamask_addr = val
            elif 'relayer' in key:
                relayer = val

    if not pk.startswith('0x'):
        pk = '0x' + pk

    print(f"[1] env2.txt: pk={len(pk)} chars, metamask={metamask_addr[:6]}****, relayer={len(relayer)} chars")

    # 2. EOA derive
    from eth_account import Account
    eoa = Account.from_key(pk).address
    print(f"[2] EOA: {eoa[:6]}****{eoa[-4:]}")
    print(f"    EOA == metamask: {eoa.lower() == metamask_addr.lower()}")

    # 3. API creds derive — her iki sig_type icin
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds, BalanceAllowanceParams, AssetType

    # sig_type=0
    sdk0 = ClobClient(host='https://clob.polymarket.com', key=pk, chain_id=137, signature_type=0)
    creds0 = sdk0.create_or_derive_api_creds()
    sdk0.set_api_creds(creds0)
    print(f"[3] sig_type=0 api_key: {creds0.api_key[:8]}****")

    # sig_type=2 funder=eoa
    sdk2 = ClobClient(host='https://clob.polymarket.com', key=pk, chain_id=137, signature_type=2, funder=eoa)
    creds2 = sdk2.create_or_derive_api_creds()
    sdk2.set_api_creds(creds2)
    print(f"    sig_type=2 api_key: {creds2.api_key[:8]}****")
    print(f"    Ayni: {creds0.api_key == creds2.api_key}")

    # 4. Balance check
    try:
        bal0 = sdk0.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, signature_type=0))
        raw0 = int(bal0.get('balance', 0))
        allow0 = bal0.get('allowances', {})
        print(f"[4] sig0 balance: ${raw0/1_000_000:.2f}")
        for c, a in allow0.items():
            a_int = int(a) if a else 0
            status = 'UNLIMITED' if a_int > 10**30 else f'${a_int/1_000_000:.2f}' if a_int > 0 else 'NONE'
            print(f"    allowance {c[:10]}...: {status}")
    except Exception as e:
        print(f"[4] sig0 balance: {e}")

    try:
        bal2 = sdk2.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, signature_type=2))
        raw2 = int(bal2.get('balance', 0))
        print(f"    sig2 balance: ${raw2/1_000_000:.2f}")
    except Exception as e:
        print(f"    sig2 balance: {e}")

    # 5. Encrypt
    from backend.auth_clients.credential_store import Credentials
    from backend.persistence.credential_persistence import save_encrypted

    final = Credentials(
        api_key=creds0.api_key,
        api_secret=creds0.api_secret,
        api_passphrase=creds0.api_passphrase,
        private_key=pk,
        funder_address=eoa,
        relayer_key=relayer,
    )
    save_encrypted(final)
    print(f"[5] Encrypted credential kaydedildi")

    # 6. Order signing test — sig_type=0
    from py_clob_client.clob_types import MarketOrderArgs, OrderType
    from py_clob_client.order_builder.constants import BUY
    from backend.auth_clients.public_client import PublicMarketClient
    from backend.discovery.engine import DiscoveryEngine

    client = PublicMarketClient(timeout_seconds=15, retry_max=2)
    engine = DiscoveryEngine(client)
    result = await engine.scan()
    now = int(time.time())
    btc = None
    for e in result.events:
        if e.asset.upper() == 'BTC':
            m = re.search(r'-(\d{10,})', e.slug)
            if m and (int(m.group(1)) - 300) <= now < int(m.group(1)):
                btc = e
                break

    if not btc:
        print("[6] BTC event bulunamadi")
        return

    token_up = btc.clob_token_ids[0]

    print(f"[6] Order test:")
    # sig_type=0 ile
    try:
        args = MarketOrderArgs(token_id=token_up, amount=1.0, side=BUY, order_type=OrderType.FOK)
        signed = sdk0.create_market_order(args)
        resp = sdk0.post_order(signed, orderType=OrderType.FOK)
        print(f"    sig0 RESPONSE: {resp}")
    except Exception as e:
        err = str(e)[:120]
        print(f"    sig0 ERROR: {err}")

    # sig_type=2 ile
    try:
        args2 = MarketOrderArgs(token_id=token_up, amount=1.0, side=BUY, order_type=OrderType.FOK)
        signed2 = sdk2.create_market_order(args2)
        resp2 = sdk2.post_order(signed2, orderType=OrderType.FOK)
        print(f"    sig2 RESPONSE: {resp2}")
    except Exception as e:
        err2 = str(e)[:120]
        print(f"    sig2 ERROR: {err2}")

    # 7. Rapor
    print()
    print("=" * 60)
    print("SIGNATURE TYPE RAPORU")
    print("=" * 60)
    print()
    print("sig_type=0 (EOA):")
    print("  Gereken: private_key + api_key + api_secret + api_passphrase")
    print("  Funder:  EOA adresi (otomatik)")
    print("  Balance: EOA'da USDC olmali")
    print()
    print("sig_type=2 (Proxy/Gnosis Safe):")
    print("  Gereken: private_key + api_key + api_secret + api_passphrase + funder_address")
    print("  Funder:  Polymarket proxy wallet adresi (polymarket.com/settings)")
    print("  Balance: Proxy wallet'ta USDC olmali")
    print("  Ek:      Proxy wallet deploy edilmis olmali (ilk Polymarket login)")

asyncio.run(main())
