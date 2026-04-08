/**
 * EventTile — 3 kolon variant container.
 *
 * Sol kolon  : kimlik + ana vurgu + (opsiyonel) aksiyon
 * Orta kolon : canli operasyon ozeti + activity satiri
 * Sag kolon  : variant'a gore teknik panel
 *               - open  -> ExitGrid (TP/SL/FS/FS PnL)
 *               - claim -> ClaimStatusPanel (status hero + retry/next + payout)
 *               - search-> RuleGrid (2x3 RuleSpec)
 *               - idle  -> IdlePanel (msg + CTA dim)
 *
 * Plan v2 madde 2: kaotik tek switch yerine kucuk local render
 * helper'lar. 4 variant icin ayri SidePanel render fonksiyonlari.
 *
 * 1. tur kompakt:
 *  - alt component'ler dosya icinde local
 *  - animasyon yok
 *  - tooltip yok (title attribute)
 *  - settings modal yok (button trigger var, tiklama no-op)
 */

import {
  COLOR,
  FONT,
  SIZE,
  PNL_TONE,
  RULE_TONE,
  ACTIVITY_TONE,
  ensureStyles,
} from './styles';
import { lookupCoin, DEFAULT_COIN_TONE, type CoinFallback } from './coinRegistry';
import type {
  PositionSummary,
  ClaimSummary,
  SearchTileContract,
  IdleTileContract,
  CoinInfoContract,
  PnlTone,
  ActivityContract,
  ClaimStatusContract,
  RuleSpecContract,
  PositionExitsContract,
} from '../api/dashboard';

// ╔══════════════════════════════════════════════════════════════╗
// ║  CSS                                                         ║
// ╚══════════════════════════════════════════════════════════════╝

ensureStyles(
  'eventtile-v51',
  `
/* tile height hesabi (defensive 850 viewport, 3 section, 4 sat = 8 tile):
 *   850 - 76(topbar) - 38(strip) - 22(content pad) - 66(3 hdr) - 15(hdr gap)
 *        - 8(inner row gap) - 20(section arasi gap) = 605
 *   605 / 4 sat = 151/sat
 *   tile internal: padding 11+11 + border 2 = 24 -> tile h ~150 */
.dsp-tile {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr) 280px;
  gap: 0;
  padding: 6px 14px;
  background: ${COLOR.bgRaised};
  border: 1px solid ${COLOR.border};
  border-radius: ${SIZE.radiusLg}px;
  font-family: ${FONT.sans};
  color: ${COLOR.text};
  height: 84px;
  align-items: stretch;
  min-width: 0;
  line-height: 1.2;
}
.dsp-tile.claim { border-color: ${COLOR.brandSoft}; }
.dsp-tile.open-profit { border-left: 3px solid ${COLOR.green}; }
.dsp-tile.open-loss   { border-left: 3px solid ${COLOR.red}; }
.dsp-tile.search      { }
.dsp-tile.idle        { opacity: 0.86; }

/* SOL kolon — 3 esit satir grid:
 *  Row 1: ID box (logo + ticker)
 *  Row 2: PnL box (big rakam ortali)
 *  Row 3: Actions row (\$/⚙ 2 col)
 * Hepsi eşit yükseklikte, hizali. */
.dsp-tile-l {
  display: grid;
  grid-template-rows: 1fr 1fr 1fr;
  gap: 6px;
  min-width: 0;
  padding-right: 14px;
  border-right: 1px solid ${COLOR.border};
}
/* ID row: 3 col grid — logo + ticker (5 char yer) + $ buton (yuvarlak, logo boyutu) */
.dsp-tile-l-id {
  display: grid;
  grid-template-columns: 22px 1fr 22px;
  align-items: center;
  gap: 6px;
  padding: 0 6px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  border-radius: ${SIZE.radius}px;
}
/* \$ buton: sadece 2 state — gri (default/passive) + yesil (active)
 * Eski dashboard stili: inline chip, container'a gomulu, mor kullanmadan */
.dsp-tile-l-id-dollar {
  width: 22px;
  height: 22px;
  display: inline-flex; align-items: center; justify-content: center;
  background: rgba(126, 126, 146, 0.16); /* gri soft default */
  border: none;
  border-radius: 50%;
  color: ${COLOR.textMuted};
  font-size: 15px;
  font-weight: ${FONT.weight.bold};
  cursor: pointer;
  font-family: ${FONT.sans};
  padding: 0;
  line-height: 1;
  flex-shrink: 0;
}
.dsp-tile-l-id-dollar.dollar-active {
  background: ${COLOR.greenSoft};
  color: ${COLOR.green};
}
.dsp-tile-l-id-dollar.dollar-passive {
  /* passive = default gri (idle tile) */
  background: rgba(126, 126, 146, 0.16);
  color: ${COLOR.textMuted};
}
.dsp-tile-l-id-dollar:hover {
  filter: brightness(1.25);
}
.dsp-tile-l-avatar {
  width: 22px; height: 22px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px;
  font-weight: ${FONT.weight.bold};
  flex-shrink: 0;
  overflow: hidden;
  border: none !important;
  background: transparent !important;
}
/* SVG logo'lari ic whitespace icerir (naturalSize 32 ama icerik %70-80).
 * Container'i %120 dolduracak sekilde scale: gercek "renkli" alan
 * dolar butonu boyutuna esitlenir. */
.dsp-tile-l-avatar img {
  width: 124%;
  height: 124%;
  object-fit: contain;
  border-radius: 50%;
}
.dsp-tile-l-symbol {
  font-size: 13px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.brand};
  letter-spacing: 0.03em;
  line-height: 1.1;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
/* PnL box (2. satir) — big rakam ortali, sadece bu kart */
.dsp-tile-l-pnl {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 8px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  border-radius: ${SIZE.radius}px;
}
.dsp-tile-l-big {
  font-family: ${FONT.mono};
  font-size: 16px;
  font-weight: ${FONT.weight.bold};
  line-height: 1;
  text-align: center;
}
.dsp-tile-l-amt {
  display: none;
}
/* Actions (3. satir) — Ayarlar butonu, PnL box ile ayni boyut */
.dsp-tile-l-actions {
  display: flex;
  min-height: 0;
}
.dsp-tile-l-act {
  flex: 1;
  display: flex; align-items: center; justify-content: center;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  border-radius: ${SIZE.radius}px;
  color: ${COLOR.textMuted};
  font-size: 12px;
  font-weight: ${FONT.weight.semibold};
  text-transform: uppercase;
  letter-spacing: 0.06em;
  cursor: pointer;
  font-family: ${FONT.sans};
  padding: 0;
  line-height: 1;
}
.dsp-tile-l-act:hover { color: ${COLOR.text}; background: ${COLOR.surfaceHover}; }
.dsp-tile-l-act.dollar-active { color: ${COLOR.green}; }
.dsp-tile-l-act.dollar-passive { color: ${COLOR.cyan}; }

/* ORTA kolon — sol panel ile birebir hizali (3 row grid)
 * Padding 0 14 -> sol/sag divider'larina sol-pad-right (14) ve sag-pad-left
 * (14) ile esit nefes. Sol+sag panellerle simetrik. */
.dsp-tile-m {
  display: grid;
  grid-template-rows: 1fr 1fr 1fr;
  gap: 6px;
  padding: 0 14px;
  min-width: 0;
}
.dsp-tile-m > *:first-child {
  grid-row: 1;
  align-self: stretch;
}
.dsp-tile-m > *:last-child {
  grid-row: 3;
  align-self: stretch;
}
/* Mid cells row — yuksek deger destegi (BTC \$111,234 / yuksek stake / DOGE delta) */
.dsp-tile-m-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 5px;
  min-width: 0;
  width: 100%;
  box-sizing: border-box;
}
.dsp-tile-m-cell {
  display: flex; flex-direction: row;
  align-items: center;
  justify-content: space-between;
  min-width: 0;
  padding: 4px 8px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  border-radius: ${SIZE.radius}px;
  gap: 6px;
  box-sizing: border-box;
}
.dsp-tile-m-row.vertical .dsp-tile-m-cell {
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3px 4px;
  gap: 0;
}
.dsp-tile-m-row.vertical .dsp-tile-m-val { text-align: center; }
.dsp-tile-m-lbl {
  font-size: 11px;
  text-transform: uppercase;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.textMuted};
  letter-spacing: 0.05em;
  white-space: nowrap;
  line-height: 1.1;
  flex-shrink: 0;
}
.dsp-tile-m-val {
  font-family: ${FONT.mono};
  font-size: 15px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.15;
  min-width: 0;
  text-align: right;
}
/* sığdır: uzun deger -> küçük font  */
.dsp-tile-m-val.fit-md { font-size: 13px; }
.dsp-tile-m-val.fit-sm { font-size: 11px; }
/* Activity bar — full width mid panel, ortali (sabit kart, gelen text ortali) */
.dsp-tile-m-act {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: center;
  padding: 4px 10px;
  background: ${COLOR.bgRaised};
  border: 1px solid ${COLOR.divider};
  border-radius: ${SIZE.radius}px;
  font-size: 12px;
  font-weight: ${FONT.weight.semibold};
  line-height: 1.2;
  width: 100%;
  text-align: center;
  box-sizing: border-box;
}
.dsp-tile-m-act-dot {
  width: 8px; height: 8px; border-radius: 50%;
  flex-shrink: 0;
}

/* SAG kolon — sol dikey divider, content dikey ortali */
.dsp-tile-r {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-left: 14px;
  border-left: 1px solid ${COLOR.border};
}

/* RuleGrid — 2 col x 3 row (kompakt sag panel icin) */
.dsp-rgrid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  width: 100%;
}
.dsp-rb {
  padding: 5px 8px;
  border-radius: ${SIZE.radius}px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  display: flex; flex-direction: column; gap: 1px;
  min-width: 0;
}
.dsp-rb-lbl {
  font-size: 9px;
  text-transform: uppercase;
  font-weight: ${FONT.weight.semibold};
  letter-spacing: 0.04em;
}
.dsp-rb-val {
  font-family: ${FONT.mono};
  font-size: ${FONT.size.md};
  font-weight: ${FONT.weight.semibold};
}

/* ExitGrid — 2x2 esik + alt 1x2 sat butonu */
.dsp-eg {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr auto;
  gap: 6px;
  width: 100%;
  height: 100%;
}
.dsp-eg-sell {
  grid-column: 1 / -1;
  padding: 7px 10px;
  border-radius: ${SIZE.radius}px;
  background: ${COLOR.redSoft};
  border: 1px solid ${COLOR.redSoft};
  color: ${COLOR.red};
  font-family: ${FONT.sans};
  font-size: 12px;
  font-weight: ${FONT.weight.bold};
  letter-spacing: 0.08em;
  text-transform: uppercase;
  text-align: center;
  cursor: pointer;
  line-height: 1.1;
}
.dsp-eg-sell.state-active:hover { filter: brightness(1.18); }
.dsp-eg-sell.state-closing,
.dsp-eg-sell.state-closed,
.dsp-eg-sell.state-pending {
  background: rgba(126,126,146,0.16);
  border-color: rgba(126,126,146,0.16);
  color: ${COLOR.textMuted};
  cursor: not-allowed;
}
/* ExitGrid cell — horizontal layout (label sol, value sag) */
.dsp-eg-cell {
  padding: 6px 11px;
  border-radius: ${SIZE.radius}px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  display: flex; flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  line-height: 1.15;
}
.dsp-eg-lbl {
  font-size: 12px;
  text-transform: uppercase;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.textMuted};
  letter-spacing: 0.06em;
  line-height: 1.1;
}
.dsp-eg-val {
  font-family: ${FONT.mono};
  font-size: 16px;
  font-weight: ${FONT.weight.bold};
  line-height: 1.15;
}
.dsp-eg-cell.tp .dsp-eg-val { color: ${COLOR.green}; }
.dsp-eg-cell.sl .dsp-eg-val { color: ${COLOR.red}; }
.dsp-eg-cell.fs .dsp-eg-val { color: ${COLOR.yellow}; }
.dsp-eg-cell.fspnl .dsp-eg-val { color: ${COLOR.red}; }

/* ClaimStatusPanel — turn 3: tone bagli + payout vurgulu */
.dsp-csp {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 5px;
  width: 100%;
}
.dsp-csp-hero {
  grid-column: 1 / -1;
  padding: 7px 12px;
  border-radius: ${SIZE.radius}px;
  display: flex; align-items: center; gap: 9px;
  /* bg + border-color inline (tone bagli) */
}
.dsp-csp-hero-dot {
  width: 9px; height: 9px; border-radius: 50%;
  flex-shrink: 0;
  /* bg + glow inline (tone bagli) */
}
.dsp-csp-hero-lbl {
  font-size: 9px; text-transform: uppercase;
  font-weight: ${FONT.weight.bold}; color: ${COLOR.textMuted};
  letter-spacing: 0.06em;
}
.dsp-csp-hero-val {
  font-family: ${FONT.mono};
  font-size: ${FONT.size.xl};
  font-weight: ${FONT.weight.bold};
  margin-left: auto;
  letter-spacing: 0.04em;
  /* color inline (tone bagli) */
}
.dsp-csp-cell {
  padding: 5px 11px;
  border-radius: ${SIZE.radius}px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  display: flex; flex-direction: column; gap: 1px;
}
.dsp-csp-cell-lbl {
  font-size: 9px; text-transform: uppercase;
  font-weight: ${FONT.weight.bold}; color: ${COLOR.textMuted};
  letter-spacing: 0.06em;
}
.dsp-csp-cell-val {
  font-family: ${FONT.mono};
  font-size: 13px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
}
.dsp-csp-payout {
  grid-column: 1 / -1;
  padding: 6px 12px;
  border-radius: ${SIZE.radius}px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  display: flex; justify-content: space-between; align-items: center;
}
.dsp-csp-payout-lbl {
  font-size: 10px; text-transform: uppercase;
  font-weight: ${FONT.weight.bold}; color: ${COLOR.textMuted};
  letter-spacing: 0.06em;
}
.dsp-csp-payout-val {
  font-family: ${FONT.mono};
  font-size: 16px;
  font-weight: ${FONT.weight.bold};
  /* color inline (tone bagli) */
}
.dsp-csp.ok .dsp-csp-payout {
  background: ${COLOR.greenSoft};
  border-color: ${COLOR.greenSoft};
}
.dsp-csp.ok .dsp-csp-payout-val { color: ${COLOR.green}; }

/* IdlePanel (sag taraf) */
.dsp-ip {
  width: 100%;
  padding: 12px;
  border-radius: ${SIZE.radius}px;
  background: ${COLOR.surface};
  border: 1px dashed ${COLOR.divider};
  color: ${COLOR.textMuted};
  font-size: ${FONT.size.sm};
  text-align: center;
}
`
);

// ╔══════════════════════════════════════════════════════════════╗
// ║  Local render helpers — sol kolon                            ║
// ╚══════════════════════════════════════════════════════════════╝

function CoinAvatar({ coin }: { coin: CoinFallback }) {
  const tone = coin.tone ?? DEFAULT_COIN_TONE;
  // Border ve bg kaldirildi (kullanici talebi) — sadece logo / harf
  if (coin.logo_url) {
    return (
      <div className="dsp-tile-l-avatar" title={coin.display_name}>
        <img
          src={coin.logo_url}
          alt={coin.symbol}
          width={22}
          height={22}
          loading="lazy"
          onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
        />
      </div>
    );
  }
  return (
    <div
      className="dsp-tile-l-avatar"
      title={coin.display_name}
      style={{ color: tone }}
    >
      {coin.symbol[0]}
    </div>
  );
}

interface SidePnlProps {
  big?: string | null;
  amount?: string | null;
  tone?: PnlTone | null;
  /** big text rengini override eder (YENİ İŞLEM cyan icin) */
  colorOverride?: string | null;
}
function SidePnl({ big, amount, tone, colorOverride }: SidePnlProps) {
  const t = tone ?? 'off';
  const fg = colorOverride ?? PNL_TONE[t].fg;
  return (
    <div className="dsp-tile-l-pnl">
      <div className="dsp-tile-l-big" style={{ color: fg }}>
        {big || '—'}
      </div>
      {amount && <div className="dsp-tile-l-amt">{amount}</div>}
    </div>
  );
}

/** TileActions — sol kolon 3. satir, 'Ayarlar' yazili tek buton
 *  PnL box ile ayni boyut. \$ artik ID row'da. */
function TileActions() {
  return (
    <div className="dsp-tile-l-actions">
      <button type="button" className="dsp-tile-l-act" title="Coin ayarları">
        Ayarlar
      </button>
    </div>
  );
}

/** DollarButton — ID row'unda ticker yaninda */
function DollarButton({ dollarState }: { dollarState?: 'active' | 'passive' }) {
  const dClass = dollarState ? `dollar-${dollarState}` : '';
  return (
    <button
      type="button"
      className={`dsp-tile-l-id-dollar ${dClass}`}
      title={
        dollarState === 'active'
          ? 'Aramada — pasife al'
          : dollarState === 'passive'
          ? 'Pasif — aramaya al'
          : 'Aktif/pasif toggle'
      }
    >
      $
    </button>
  );
}

function CoinIdentityBlock({
  coin,
  big,
  amount,
  tone,
  dollarState,
  bigColor,
}: {
  coin: CoinFallback;
  big?: string | null;
  amount?: string | null;
  tone?: PnlTone | null;
  dollarState?: 'active' | 'passive';
  /** PnL big text rengi override (YENİ İŞLEM cyan icin) */
  bigColor?: string | null;
}) {
  return (
    <div className="dsp-tile-l">
      <div className="dsp-tile-l-id" title={coin.display_name}>
        <CoinAvatar coin={coin} />
        <span className="dsp-tile-l-symbol">{coin.symbol}</span>
        <DollarButton dollarState={dollarState} />
      </div>
      <SidePnl big={big} amount={amount} tone={tone} colorOverride={bigColor} />
      <TileActions />
    </div>
  );
}

// ╔══════════════════════════════════════════════════════════════╗
// ║  Local render helpers — orta kolon                           ║
// ╚══════════════════════════════════════════════════════════════╝

interface MidCellsProps {
  cells: Array<{ label: string; value: string; color?: string; title?: string }>;
  vertical?: boolean;
  hideLabels?: boolean;
}
function fitClass(v: string): string {
  const len = v.length;
  if (len >= 9) return 'dsp-tile-m-val fit-sm';
  if (len >= 7) return 'dsp-tile-m-val fit-md';
  return 'dsp-tile-m-val';
}
function MidCells({ cells, vertical, hideLabels }: MidCellsProps) {
  return (
    <div className={`dsp-tile-m-row${vertical ? ' vertical' : ''}`}>
      {cells.map((c) => (
        <div key={c.label} className="dsp-tile-m-cell" title={c.title}>
          {!hideLabels && <div className="dsp-tile-m-lbl">{c.label}</div>}
          <div className={fitClass(c.value)} style={c.color ? { color: c.color } : undefined}>{c.value}</div>
        </div>
      ))}
    </div>
  );
}

/** Parantezli sıfır sayısı (CoinGecko mantığı, okunur).
 *  -0.000025 -> "-0.0(4)25"  (decimal sonrası 4 sıfır, sonra 25) */
function tinyFormat(n: number): string | null {
  if (n === 0) return null;
  const sign = n < 0 ? '-' : '';
  const a = Math.abs(n);
  const str = a.toFixed(20).replace(/0+$/, '');
  const m = str.match(/^0\.(0+)(\d+)$/);
  if (!m) return null;
  const zeros = m[1].length;
  if (zeros < 2) return null;
  const digits = m[2].slice(0, 3);
  return `${sign}0.0(${zeros})${digits}`;
}

/** Compact numeric formatter — büyük sayıları K/M, çok küçükleri 0.0₄25 stiline indirir.
 *  Tam değer tooltip'te kalır.
 *  "$1000.00" -> "$1.00K"; "-15234.50" -> "-15.2K"; "-0.000025" -> "-0.0₄25"
 */
function compactNumber(raw: string | null | undefined): { display: string; title?: string } {
  if (!raw) return { display: '—' };
  const m = raw.match(/^([+-]?)(\$?)(\d+(?:[.,]\d+)?)(.*)$/);
  if (!m) return { display: raw };
  const [, sign, dollar, numStr, suffix] = m;
  const n = parseFloat((sign === '-' ? '-' : '') + numStr.replace(',', '.'));
  if (isNaN(n)) return { display: raw };
  const abs = Math.abs(n);
  // Çok küçük değerler -> CoinGecko subscript notasyonu
  if (abs > 0 && abs < 0.01) {
    const tiny = tinyFormat(n);
    if (tiny) return { display: dollar + tiny + (suffix || ''), title: raw };
    return { display: '≈0', title: raw };
  }
  if (abs >= 1_000_000) return { display: (n / 1_000_000).toFixed(1) + 'M' + (suffix || ''), title: raw };
  if (abs >= 10_000)    return { display: (n / 1_000).toFixed(1) + 'K' + (suffix || ''), title: raw };
  if (abs >= 1_000)     return { display: (n / 1_000).toFixed(2) + 'K' + (suffix || ''), title: raw };
  return { display: raw };
}

/** signed numeric → color (+ green, - red, 0 muted) */
function signColor(raw: string | null | undefined): string | undefined {
  if (!raw) return undefined;
  const m = raw.match(/(-?\d+(?:\.\d+)?)/);
  if (!m) return undefined;
  const n = parseFloat(m[1]);
  if (n > 0) return COLOR.green;
  if (n < 0) return COLOR.red;
  return COLOR.textMuted;
}

function ActivityStatusLine({
  activity,
}: {
  activity?: ActivityContract | null;
}) {
  if (!activity || !activity.text) return null;
  const tone = ACTIVITY_TONE[activity.severity ?? 'info'];
  return (
    <div
      className="dsp-tile-m-act"
      style={{
        color: tone.fg,
        borderColor: `${tone.fg}33`,
      }}
    >
      <span
        className="dsp-tile-m-act-dot"
        style={{
          background: tone.dot,
          boxShadow: `0 0 6px ${tone.dot}aa`,
        }}
      />
      <span>{activity.text}</span>
    </div>
  );
}

// ╔══════════════════════════════════════════════════════════════╗
// ║  Local render helpers — sag kolon (variant panels)           ║
// ╚══════════════════════════════════════════════════════════════╝

function RuleGrid({ rules }: { rules: RuleSpecContract[] }) {
  if (!rules || rules.length === 0) {
    return <div className="dsp-ip">Kural verisi yok</div>;
  }
  return (
    <div className="dsp-rgrid">
      {rules.map((r, i) => {
        const t = RULE_TONE[r.state];
        return (
          <div
            key={`${r.label}-${i}`}
            className="dsp-rb"
            style={{ borderColor: t.border, background: t.bg }}
            title={r.threshold_text ?? undefined}
          >
            <div className="dsp-rb-lbl" style={{ color: t.fg }}>
              {r.label}
            </div>
            <div className="dsp-rb-val" style={{ color: t.fg }}>
              {r.live_value}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Mock-derive sell button state from activity text. v0.5.x'te gerçek lifecycle_state ile değişecek. */
type SellState = 'active' | 'closing' | 'closed' | 'pending';
function deriveSellState(activityText: string | null | undefined): SellState {
  const t = activityText ?? '';
  if (/ile kapandı|kapandı$/i.test(t)) return 'closed';
  if (/TP @|SL tetik|FS @|kapatma emri|satış emri/i.test(t)) return 'closing';
  if (/dolum bekleniyor|gönderiliyor/i.test(t)) return 'pending';
  return 'active';
}
function sellLabel(s: SellState): string {
  if (s === 'closed') return 'KAPANDI';
  if (s === 'closing') return 'KAPANIYOR';
  if (s === 'pending') return 'BEKLİYOR';
  return 'ŞİMDİ SAT';
}

function ExitGrid({
  exits,
  sellState = 'active',
}: {
  exits?: PositionExitsContract | null;
  sellState?: SellState;
}) {
  if (!exits) return <div className="dsp-ip">Cıkıs esikleri yok</div>;
  const disabled = sellState !== 'active';
  return (
    <div className="dsp-eg">
      <div className="dsp-eg-cell tp">
        <div className="dsp-eg-lbl">TP</div>
        <div className="dsp-eg-val">{exits.tp}</div>
      </div>
      <div className="dsp-eg-cell sl">
        <div className="dsp-eg-lbl">SL</div>
        <div className="dsp-eg-val">{exits.sl}</div>
      </div>
      <div className="dsp-eg-cell fs">
        <div className="dsp-eg-lbl">FS/Z</div>
        <div className="dsp-eg-val">{exits.fs}</div>
      </div>
      <div className="dsp-eg-cell fspnl">
        <div className="dsp-eg-lbl">FS/P</div>
        <div className="dsp-eg-val">{exits.fs_pnl ?? '—'}</div>
      </div>
      <button
        type="button"
        className={`dsp-eg-sell state-${sellState}`}
        disabled={disabled}
        title={disabled ? 'Manuel kapatma şu an pasif' : 'Manuel kapatma (Market FOK)'}
      >
        {sellLabel(sellState)}
      </button>
    </div>
  );
}

interface ClaimPanelProps {
  status: ClaimStatusContract | null | undefined; // RETRY/OK/FAIL
  retry: number | null | undefined;
  maxRetry: number | null | undefined;
  nextSec: number | null | undefined;
  payout: string | null | undefined;
}

/** Claim status -> tone (RETRY=yellow, OK=green, FAIL=red, null=brand). */
function claimTone(status: ClaimStatusContract | null | undefined): {
  fg: string;
  bg: string;
  glow: string;
  klass: string;
} {
  switch (status) {
    case 'OK':
      return { fg: COLOR.green, bg: COLOR.greenSoft, glow: COLOR.greenGlow, klass: 'ok' };
    case 'FAIL':
      return { fg: COLOR.red, bg: COLOR.redSoft, glow: COLOR.redGlow, klass: 'fail' };
    case 'RETRY':
      return { fg: COLOR.yellow, bg: COLOR.yellowSoft, glow: COLOR.yellowGlow, klass: 'retry' };
    default:
      return { fg: COLOR.brand, bg: COLOR.brandSoft, glow: COLOR.brandGlow, klass: 'pending' };
  }
}

/** Claim status TR display label */
function trClaimStatus(status: ClaimStatusContract | null | undefined): string {
  switch (status) {
    case 'OK': return 'BAŞARILI';
    case 'FAIL': return 'BAŞARISIZ';
    case 'RETRY': return 'TEKRAR';
    default: return '—';
  }
}

function ClaimStatusPanel({
  status,
  retry,
  maxRetry,
  nextSec,
  payout,
}: ClaimPanelProps) {
  const tone = claimTone(status);
  return (
    <div className={`dsp-csp ${tone.klass}`}>
      <div
        className="dsp-csp-hero"
        style={{
          background: tone.bg,
          border: `1px solid ${tone.fg}55`,
        }}
      >
        <span
          className="dsp-csp-hero-dot"
          style={{
            background: tone.fg,
            boxShadow: `0 0 6px ${tone.fg}99`,
          }}
        />
        <span className="dsp-csp-hero-lbl">DURUM</span>
        <span className="dsp-csp-hero-val" style={{ color: tone.fg }}>
          {trClaimStatus(status)}
        </span>
      </div>
      <div className="dsp-csp-cell">
        <div className="dsp-csp-cell-lbl">Retry</div>
        <div className="dsp-csp-cell-val">
          {retry != null ? `${retry}/${maxRetry ?? '?'}` : '—'}
        </div>
      </div>
      <div className="dsp-csp-cell">
        <div className="dsp-csp-cell-lbl">Next</div>
        <div className="dsp-csp-cell-val">
          {nextSec != null ? `${nextSec}s` : '—'}
        </div>
      </div>
      <div className="dsp-csp-payout">
        <span className="dsp-csp-payout-lbl">Tahsil</span>
        <span
          className="dsp-csp-payout-val"
          style={{
            color: status === 'OK' ? COLOR.green : COLOR.text,
          }}
        >
          {payout ?? '—'}
        </span>
      </div>
    </div>
  );
}

function IdlePanel({ msg }: { msg: string }) {
  return <div className="dsp-ip">{msg}</div>;
}

// ╔══════════════════════════════════════════════════════════════╗
// ║  Variant body renderers (orta kolon, variant'a gore)         ║
// ╚══════════════════════════════════════════════════════════════╝

function OpenBody({
  position,
  activity,
}: {
  position: PositionSummary;
  activity?: ActivityContract | null;
}) {
  const live = position.live;
  // Row 1 — Giris / Canli / Delta
  const sideColor = live ? (live.side === 'UP' ? COLOR.green : COLOR.red) : undefined;
  const cLive = live ? compactNumber(live.live) : { display: '—' };
  const cDelta = live ? compactNumber(live.delta_text) : { display: '—' };
  const liveCells = live
    ? [
        { label: 'Giriş', value: `${live.side === 'UP' ? '▲' : '▼'} ${live.entry}`, color: sideColor },
        { label: 'Canlı', value: cLive.display, title: cLive.title, color: signColor(live.delta_text) ?? COLOR.text },
        { label: 'Delta', value: cDelta.display, title: cDelta.title, color: signColor(live.delta_text) },
      ]
    : [];
  // Row 2 — Maliyet / NET PNL % / NET PNL USD
  const costRaw = position.requested_amount_usd != null
    ? `$${position.requested_amount_usd.toFixed(2)}`
    : '—';
  const netPct = position.pnl_big ?? '—';
  const netUsdRaw = position.pnl_amount ?? '—';
  const cCost = compactNumber(costRaw);
  const cNetUsd = compactNumber(netUsdRaw);
  const pnlColor = position.pnl_tone ? PNL_TONE[position.pnl_tone].fg : undefined;
  const pnlCells = [
    { label: 'Tutar', value: cCost.display, title: cCost.title, color: COLOR.cyan },
    { label: 'PNL%', value: netPct, color: pnlColor },
    { label: 'USD', value: cNetUsd.display, title: cNetUsd.title, color: pnlColor },
  ];
  return (
    <div className="dsp-tile-m">
      <MidCells cells={pnlCells} />
      {liveCells.length > 0 && <MidCells cells={liveCells} />}
      <ActivityStatusLine activity={activity} />
    </div>
  );
}

/** Close reason TR: 'expiry' -> 'SÜRE DOLDU' */
function trCloseReason(reason: string | null): string {
  if (!reason) return '—';
  const r = reason.toLowerCase();
  if (r === 'expiry') return 'SÜRE DOLDU';
  if (r === 'tp') return 'TP';
  if (r === 'sl') return 'SL';
  if (r === 'fs' || r === 'force_sell') return 'FS';
  if (r === 'manual') return 'MANUEL';
  return reason.toUpperCase();
}

/** Outcome TR: WIN/LOSS/PENDING -> KAZANÇ/KAYIP/BEKLİYOR */
function trOutcome(net: number, closeReason: string | null): string {
  if (net > 0) return 'KAZANÇ';
  if (net < 0) return 'KAYIP';
  if ((closeReason ?? '').toLowerCase() === 'expiry') return 'BEKLİYOR';
  return '—';
}

function ClaimBody({
  position,
  activity,
}: {
  position: PositionSummary;
  activity?: ActivityContract | null;
}) {
  // Q3=a karari: KAPANIS -> SONUC -> GIRIS
  const closeText = trCloseReason(position.close_reason);
  const outcome = trOutcome(position.net_realized_pnl, position.close_reason);
  // fill_price 0-1 range raw, display 0-100 (Polymarket share cents)
  // 0.65 -> 65
  const side = position.side ?? position.live?.side ?? 'UP';
  const arrow = side === 'UP' ? '▲' : '▼';
  const entry = `${arrow} ${Math.round(position.fill_price * 100)}`;
  const entryColor = side === 'UP' ? COLOR.green : COLOR.red;

  const closeColor =
    closeText === 'TP' ? COLOR.green :
    closeText === 'SL' ? COLOR.red :
    closeText === 'FS' ? COLOR.yellow :
    closeText === 'SÜRE DOLDU' ? COLOR.yellow :
    COLOR.text;
  const outcomeColor =
    outcome === 'KAZANÇ' ? COLOR.green :
    outcome === 'KAYIP' ? COLOR.red :
    outcome === 'BEKLİYOR' ? COLOR.yellow :
    COLOR.text;
  return (
    <div className="dsp-tile-m">
      <MidCells
        vertical
        hideLabels
        cells={[
          { label: 'Kapanış', value: closeText, color: closeColor },
          { label: 'Sonuç', value: outcome, color: outcomeColor },
          { label: 'Giriş', value: entry, color: entryColor },
        ]}
      />
      <ActivityStatusLine activity={activity} />
    </div>
  );
}

function SearchBody({
  ptb,
  live,
  delta,
  activity,
}: {
  ptb: string;
  live: string;
  delta: string;
  activity?: ActivityContract | null;
}) {
  return (
    <div className="dsp-tile-m">
      <MidCells
        cells={[
          { label: 'PTB', value: compactNumber(ptb).display, title: compactNumber(ptb).title, color: COLOR.yellow },
          { label: 'Canlı', value: compactNumber(live).display, title: compactNumber(live).title, color: signColor(delta) ?? COLOR.text },
          { label: 'Delta', value: compactNumber(delta).display, title: compactNumber(delta).title, color: signColor(delta) ?? COLOR.yellow },
        ]}
      />
      <ActivityStatusLine activity={activity} />
    </div>
  );
}

function IdleBody({ msg, activity }: { msg: string; activity?: ActivityContract | null }) {
  return (
    <div className="dsp-tile-m">
      <div className="dsp-tile-m-row">
        <div className="dsp-tile-m-cell">
          <div className="dsp-tile-m-val" style={{ color: COLOR.textMuted }}>
            {msg}
          </div>
        </div>
      </div>
      <ActivityStatusLine activity={activity} />
    </div>
  );
}

// ╔══════════════════════════════════════════════════════════════╗
// ║  Variant tile components (4 ayri small fn)                   ║
// ╚══════════════════════════════════════════════════════════════╝

/** deriveOpenStatus — activity text + tone'dan lifecycle status etiketi.
 *  TR cevrilmis: YENİ İŞLEM / TP-YAKIN / TP-KAR / SL-YAKIN / STOPLOSS /
 *  F-RISK / FORCESELL / KAR / ZARAR / — */
function deriveOpenStatus(position: PositionSummary): string {
  const text = position.activity?.text ?? '';
  // Lifecycle pattern eslestirme (en spesifikten en genele)
  if (/Emir doldu|pozisyon a[çc]ild/i.test(text)) return 'YENİ İŞLEM';
  if (/TP\s*tetik|TP\s*@/i.test(text)) return 'TP-KAR';
  if (/TP\s*yakla[şs]/i.test(text)) return 'TP-YAKIN';
  if (/SL\s*tetik|SL\s*@/i.test(text)) return 'STOPLOSS';
  if (/SL\s*yakla[şs]/i.test(text)) return 'SL-YAKIN';
  if (/Force\s*sell\s*—?\s*\d+\s*saniye|FS\s*countdown/i.test(text)) return 'FS-YAKIN';
  if (/Force\s*sell|FS\s*@/i.test(text)) return 'FORCESELL';
  if (position.pnl_tone === 'profit') return 'KAR';
  if (position.pnl_tone === 'loss') return 'ZARAR';
  return '—';
}

/** Open status -> color override (YENİ İŞLEM cyan, digerleri pnl_tone) */
function openStatusColor(label: string, pnlTone: PnlTone | null | undefined): string | null {
  if (label === 'YENİ İŞLEM') return COLOR.cyan;
  // Diger label'lar pnl_tone uzerinden PNL_TONE[].fg kullanir (SidePnl default)
  if (pnlTone) return PNL_TONE[pnlTone].fg;
  return null;
}

function OpenTile({
  position,
  coins,
}: {
  position: PositionSummary;
  coins: CoinInfoContract[] | null;
}) {
  const coin = lookupCoin(position.asset, coins);
  const tone = position.pnl_tone ?? null;
  const klass =
    tone === 'profit'
      ? 'dsp-tile open-profit'
      : tone === 'loss'
      ? 'dsp-tile open-loss'
      : 'dsp-tile';
  // Sol kolon PnL box: islem durumu (YENİ İŞLEM / TP-YAKIN / TP-KAR / SL-YAKIN /
  // STOPLOSS / F-RISK / FORCESELL / KAR / ZARAR)
  const statusLabel = deriveOpenStatus(position);
  const statusColor = openStatusColor(statusLabel, tone);
  return (
    <div className={klass}>
      <CoinIdentityBlock
        coin={coin}
        big={statusLabel}
        amount={null}
        tone={tone}
        bigColor={statusColor}
      />
      <OpenBody position={position} activity={position.activity} />
      <div className="dsp-tile-r">
        <ExitGrid exits={position.exits} sellState={deriveSellState(position.activity?.text)} />
      </div>
    </div>
  );
}

function ClaimTile({
  position,
  coins,
  claims,
}: {
  position: PositionSummary;
  coins: CoinInfoContract[] | null;
  claims: ClaimSummary[] | null;
}) {
  const coin = lookupCoin(position.asset, coins);
  // turn 3: claims listesinden lookup (position_id eslesmesi)
  const claim = claims?.find((c) => c.position_id === position.position_id);
  return (
    <div className="dsp-tile claim">
      <CoinIdentityBlock
        coin={coin}
        big={position.pnl_big ?? 'CLAIM'}
        amount={position.pnl_amount ?? 'PENDING'}
        tone={position.pnl_tone ?? 'pending'}
      />
      <ClaimBody position={position} activity={position.activity} />
      <div className="dsp-tile-r">
        <ClaimStatusPanel
          status={claim?.status ?? null}
          retry={claim?.retry ?? null}
          maxRetry={claim?.max_retry ?? null}
          nextSec={claim?.next_sec ?? null}
          payout={claim?.payout ?? null}
        />
      </div>
    </div>
  );
}

function SearchTile({
  tile,
  coins,
}: {
  tile: SearchTileContract;
  coins: CoinInfoContract[] | null;
}) {
  const coin = lookupCoin(tile.coin, coins);
  return (
    <div className="dsp-tile search">
      <CoinIdentityBlock
        coin={coin}
        big={tile.pnl_big}
        amount={tile.pnl_amount ?? null}
        tone={tile.pnl_tone}
        dollarState="active"
      />
      <SearchBody
        ptb={tile.ptb}
        live={tile.live}
        delta={tile.delta}
        activity={tile.activity}
      />
      <div className="dsp-tile-r">
        <RuleGrid rules={tile.rules} />
      </div>
    </div>
  );
}

function IdleTile({
  tile,
  coins,
}: {
  tile: IdleTileContract;
  coins: CoinInfoContract[] | null;
}) {
  const coin = lookupCoin(tile.coin ?? '?', coins);
  return (
    <div className="dsp-tile idle">
      <CoinIdentityBlock
        coin={coin}
        big="OFF"
        amount={null}
        tone="off"
        dollarState="passive"
      />
      <IdleBody msg={tile.msg} activity={tile.activity} />
      <div className="dsp-tile-r">
        {tile.rules && tile.rules.length > 0 ? (
          <RuleGrid rules={tile.rules} />
        ) : (
          <IdlePanel msg={`Kategori: ${tile.idle_kind}`} />
        )}
      </div>
    </div>
  );
}

// ╔══════════════════════════════════════════════════════════════╗
// ║  Public EventTile — variant container                        ║
// ╚══════════════════════════════════════════════════════════════╝

export type EventTileVariant = 'open' | 'claim' | 'search' | 'idle';

export interface EventTileProps {
  variant: EventTileVariant;
  /** open + claim variant icin */
  position?: PositionSummary;
  /** search variant icin */
  search?: SearchTileContract;
  /** idle variant icin */
  idle?: IdleTileContract;
  /** coin metadata lookup icin */
  coins: CoinInfoContract[] | null;
  /** claim variant icin claim status lookup (position_id eslesmesi) */
  claims?: ClaimSummary[] | null;
}

export default function EventTile(props: EventTileProps) {
  switch (props.variant) {
    case 'open':
      if (!props.position) return null;
      return <OpenTile position={props.position} coins={props.coins} />;
    case 'claim':
      if (!props.position) return null;
      return (
        <ClaimTile
          position={props.position}
          coins={props.coins}
          claims={props.claims ?? null}
        />
      );
    case 'search':
      if (!props.search) return null;
      return <SearchTile tile={props.search} coins={props.coins} />;
    case 'idle':
      if (!props.idle) return null;
      return <IdleTile tile={props.idle} coins={props.coins} />;
    default:
      return null;
  }
}
