/**
 * coinRegistry — frontend coin metadata fallback.
 *
 * Backend `/api/dashboard/coins` provider yoksa veya bos donerse,
 * frontend bu statik registry'e duser. Backend tarafindaki
 * `_COIN_METADATA_FALLBACK` aynasi.
 *
 * Yeni coin eklemek icin: bu dict'e bir entry ekle.
 *
 * Reusable: bu dosya sadece preview'da degil, baska sayfalarda da
 * kullanilabilir. coin sembolu ile lookup yapar.
 */

export interface CoinFallback {
  symbol: string;
  display_name: string;
  /** logoUrl: optional asset path veya CDN url. Yoksa harf avatar. */
  logo_url?: string;
}

export const COIN_FALLBACK: Record<string, CoinFallback> = {
  BTC: { symbol: 'BTC', display_name: 'Bitcoin' },
  ETH: { symbol: 'ETH', display_name: 'Ethereum' },
  SOL: { symbol: 'SOL', display_name: 'Solana' },
  XRP: { symbol: 'XRP', display_name: 'Ripple' },
  DOGE: { symbol: 'DOGE', display_name: 'Dogecoin' },
  ADA: { symbol: 'ADA', display_name: 'Cardano' },
  MATIC: { symbol: 'MATIC', display_name: 'Polygon' },
  BNB: { symbol: 'BNB', display_name: 'BNB' },
  LINK: { symbol: 'LINK', display_name: 'Chainlink' },
};

/**
 * Coin lookup — backend coins listesi ile fallback registry'i birlestir.
 *
 * Once backend `coins` listesinde ara, yoksa fallback'e dus, oda yoksa
 * yalin sembol dondur (display_name = symbol).
 *
 * Kullanim:
 *   const meta = lookupCoin('BTC', backendCoins);
 *   meta.display_name → 'Bitcoin'
 */
export function lookupCoin(
  symbol: string,
  backendCoins?: Array<{ symbol: string; display_name?: string | null; logo_url?: string | null }> | null
): CoinFallback {
  const sym = symbol.toUpperCase();

  // 1. Backend coins (varsa)
  if (backendCoins) {
    const found = backendCoins.find((c) => c.symbol.toUpperCase() === sym);
    if (found) {
      return {
        symbol: sym,
        display_name: found.display_name || sym,
        logo_url: found.logo_url ?? undefined,
      };
    }
  }

  // 2. Fallback registry
  if (COIN_FALLBACK[sym]) {
    return COIN_FALLBACK[sym];
  }

  // 3. Yalin
  return { symbol: sym, display_name: sym };
}
