"""Tum acik pozisyonlari kapat."""
import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

async def main():
    import httpx
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import MarketOrderArgs, OrderType, BalanceAllowanceParams, AssetType
    from py_clob_client.order_builder.constants import SELL
    from backend.persistence.credential_persistence import load_encrypted

    polymarket_addr = '0xd019B11c6572eCDb8F0036787f853Ef1A7EC2535'
    creds = load_encrypted()
    pk = creds.private_key
    if not pk.startswith('0x'):
        pk = '0x' + pk

    sdk = ClobClient(host='https://clob.polymarket.com', key=pk, chain_id=137,
                     signature_type=2, funder=polymarket_addr)
    api = sdk.create_or_derive_api_creds()
    sdk.set_api_creds(api)

    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get('https://data-api.polymarket.com/positions',
                        params={'user': polymarket_addr, 'sizeThreshold': '0.001'})
        positions = r.json() if r.status_code == 200 else []
        print(f"Acik pozisyon: {len(positions)}")
        for pos in positions:
            token = pos.get('asset', '')
            size = float(pos.get('size', 0))
            title = pos.get('title', '')[:60]
            print(f"  {title} size={size}")
            if size > 0.001:
                try:
                    args = MarketOrderArgs(token_id=token, amount=size, side=SELL, order_type=OrderType.FOK)
                    signed = sdk.create_market_order(args)
                    resp = sdk.post_order(signed, orderType=OrderType.FOK)
                    if isinstance(resp, dict) and resp.get('success'):
                        taking = resp.get('takingAmount', '?')
                        print(f"    SATILDI: +${taking} USDC")
                    else:
                        print(f"    SATILAMADI")
                except Exception as e:
                    print(f"    HATA: {str(e)[:80]}")

    bal = sdk.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, signature_type=2))
    raw = int(bal.get('balance', 0))
    print(f"Balance: ${raw/1_000_000:.2f}")

if __name__ == '__main__':
    asyncio.run(main())
