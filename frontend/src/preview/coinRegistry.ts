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
  /** Marka rengi — avatar tone aksami. Bilinmeyen coin -> brand mor. */
  tone?: string;
}

/**
 * COIN_TONE — coin marka renkleri (avatar aksami icin).
 * Yalnizca avatar bg ve border'da SOFT olarak kullanilir, kart geneli
 * dark+brand temasi ile celismez.
 *
 * Bilinmeyen coin -> brand mor (Q2=a karari).
 */
export const COIN_TONE: Record<string, string> = {
  BTC:   '#f7931a', // bitcoin orange
  ETH:   '#627eea', // ethereum blue
  SOL:   '#9945ff', // solana purple
  DOGE:  '#c2a633', // dogecoin gold
  XRP:   '#23292f', // ripple dark gray (gorunsun diye soft kullanilacak)
  ADA:   '#0033ad', // cardano blue
  MATIC: '#8247e5', // polygon purple
  BNB:   '#f0b90b', // bnb yellow
  LINK:  '#2a5ada', // chainlink blue
};

/** Bilinmeyen coin fallback tone — brand cyan. */
export const DEFAULT_COIN_TONE = '#06b6d4';

/**
 * Logo CDN — atomiclabs/cryptocurrency-icons (jsdelivr).
 * Color SVG, ~32x32, public CDN, free, no auth.
 */
const LOGO_CDN = 'https://cdn.jsdelivr.net/gh/atomiclabs/cryptocurrency-icons@1a63530/svg/color';
const logoUrl = (sym: string) => `${LOGO_CDN}/${sym.toLowerCase()}.svg`;

export const COIN_FALLBACK: Record<string, CoinFallback> = {
  BTC:   { symbol: 'BTC',   display_name: 'Bitcoin',   tone: COIN_TONE.BTC,   logo_url: logoUrl('btc') },
  ETH:   { symbol: 'ETH',   display_name: 'Ethereum',  tone: COIN_TONE.ETH,   logo_url: logoUrl('eth') },
  SOL:   { symbol: 'SOL',   display_name: 'Solana',    tone: COIN_TONE.SOL,   logo_url: logoUrl('sol') },
  XRP:   { symbol: 'XRP',   display_name: 'Ripple',    tone: COIN_TONE.XRP,   logo_url: logoUrl('xrp') },
  DOGE:  { symbol: 'DOGE',  display_name: 'Dogecoin',  tone: COIN_TONE.DOGE,  logo_url: logoUrl('doge') },
  ADA:   { symbol: 'ADA',   display_name: 'Cardano',   tone: COIN_TONE.ADA,   logo_url: logoUrl('ada') },
  MATIC: { symbol: 'MATIC', display_name: 'Polygon',   tone: COIN_TONE.MATIC, logo_url: logoUrl('matic') },
  BNB:   { symbol: 'BNB',   display_name: 'BNB',       tone: COIN_TONE.BNB,   logo_url: logoUrl('bnb') },
  LINK:  { symbol: 'LINK',  display_name: 'Chainlink', tone: COIN_TONE.LINK,  logo_url: logoUrl('link') },
  AVAX:  { symbol: 'AVAX',  display_name: 'Avalanche', tone: '#e84142',       logo_url: logoUrl('avax') },
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
  const fallback = COIN_FALLBACK[sym];

  // 1. Backend coins (varsa) — logo_url yoksa fallback'tan tamamla
  if (backendCoins) {
    const found = backendCoins.find((c) => c.symbol.toUpperCase() === sym);
    if (found) {
      return {
        symbol: sym,
        display_name: found.display_name || fallback?.display_name || sym,
        // Backend logo_url yoksa fallback registry'den cek (bizim CDN url'leri)
        logo_url: found.logo_url ?? fallback?.logo_url,
        tone: COIN_TONE[sym] ?? fallback?.tone ?? DEFAULT_COIN_TONE,
      };
    }
  }

  // 2. Fallback registry
  if (fallback) {
    return fallback;
  }

  // 3. Yalin (bilinmeyen coin -> brand mor tone)
  return { symbol: sym, display_name: sym, tone: DEFAULT_COIN_TONE };
}
