/**
 * OpenRail — açık işlemler sağ yan panelde dikey kart listesi.
 * NotifRail ile aynı kart iskeleti; ama pozisyon bilgisi: coin + yön + PnL +
 * giriş + canlı + kısa durum.
 */

import { COLOR, FONT, SIZE, PNL_TONE, ensureStyles } from './styles';
import { COIN_FALLBACK } from './coinRegistry';
import type { PositionSummary } from '../api/dashboard';

ensureStyles(
  'openrail-v12',
  `
.dsp-orail {
  width: 100%;
  flex-shrink: 0;
  background: ${COLOR.bg};
  border-left: 1px solid ${COLOR.border};
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.dsp-orail-hdr {
  height: 56px;
  flex-shrink: 0;
  padding: 0 14px;
  border-bottom: 1px solid ${COLOR.border};
  display: flex;
  align-items: center;
  gap: 8px;
}
.dsp-orail-hdr-title {
  font-size: 11px;
  font-weight: ${FONT.weight.bold};
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: ${COLOR.textMuted};
}
.dsp-orail-hdr-badge {
  font-family: ${FONT.mono};
  font-size: 10px;
  font-weight: ${FONT.weight.bold};
  padding: 1px 7px;
  border-radius: 9px;
  background: ${COLOR.greenSoft};
  color: ${COLOR.green};
  border: 1px solid ${COLOR.greenSoft};
}
.dsp-orail-list {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 6px 10px 8px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-auto-rows: calc((100% - 12px) / 3);
  gap: 6px;
  scrollbar-color: ${COLOR.green} transparent;
  scrollbar-width: thin;
}
.dsp-orail-list::-webkit-scrollbar { width: 8px; }
.dsp-orail-list::-webkit-scrollbar-track { background: transparent; }
.dsp-orail-list::-webkit-scrollbar-thumb {
  background: ${COLOR.green};
  border-radius: 4px;
}
.dsp-orail-list::-webkit-scrollbar-thumb:hover {
  background: #16a34a;
}

/* Kart — 3 micro-row: header (logo+ticker+durum), money (pnl%+usd), prices (giriş/canlı/delta) */
.dsp-ocard {
  min-height: 0;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  border-left-width: 3px;
  border-radius: ${SIZE.radius}px;
  padding: 14px 16px;
  display: grid;
  grid-template-columns: auto 1fr auto;
  grid-template-rows: auto 1fr auto;
  column-gap: 14px;
  row-gap: 8px;
  min-width: 0;
  overflow: hidden;
}

/* Row 1 col 1: logo */
.dsp-ocard-logo {
  grid-column: 1;
  grid-row: 1;
  width: 44px; height: 44px;
  border-radius: 50%;
  background: ${COLOR.bg};
  display: flex; align-items: center; justify-content: center;
  overflow: hidden;
  flex-shrink: 0;
}
/* Row 1 col 2: ticker + side row */
.dsp-ocard-id {
  grid-column: 2;
  grid-row: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.dsp-ocard-id-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dsp-ocard-ticker {
  font-size: 20px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
  letter-spacing: 0.02em;
}
.dsp-ocard-side {
  font-family: ${FONT.mono};
  font-size: 13px;
  font-weight: ${FONT.weight.bold};
}
.dsp-ocard-status {
  align-self: flex-start;
  font-family: ${FONT.mono};
  font-size: 9px;
  font-weight: ${FONT.weight.bold};
  letter-spacing: 0.07em;
  text-transform: uppercase;
  padding: 2px 6px;
  border-radius: 6px;
  border: 1px solid ${COLOR.divider};
  color: ${COLOR.textMuted};
}

/* Row 1 col 3: PNL% hero + USD */
.dsp-ocard-pnl {
  grid-column: 3;
  grid-row: 1;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  min-width: 0;
}
.dsp-ocard-pct {
  font-family: ${FONT.mono};
  font-size: 26px;
  font-weight: ${FONT.weight.bold};
  line-height: 1;
  letter-spacing: -0.02em;
}
.dsp-ocard-usd {
  font-family: ${FONT.mono};
  font-size: 12px;
  font-weight: ${FONT.weight.bold};
}

/* Row 2 (span 3): info cells — Tutar / Giriş / Canlı / Delta */
.dsp-ocard-cells {
  grid-column: 1 / -1;
  grid-row: 2;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
  align-self: center;
}

/* Row 3 (span 3): exits + sell */
.dsp-ocard-bottom {
  grid-column: 1 / -1;
  grid-row: 3;
  display: grid;
  grid-template-columns: 1fr 1fr 1fr auto;
  gap: 6px;
  align-items: center;
}
.dsp-ocard-exits {
  display: contents;
}
.dsp-ocard-sell-wrap {
  display: contents;
}
.dsp-ocard.tone-profit { border-left-color: ${COLOR.green}; }
.dsp-ocard.tone-loss   { border-left-color: ${COLOR.red}; }
.dsp-ocard.tone-neutral,
.dsp-ocard.tone-off    { border-left-color: ${COLOR.divider}; }
.dsp-ocard.tone-pending { border-left-color: ${COLOR.yellow}; }

/* Row 1: logo + ticker + side + big pnl + status badge */
.dsp-ocard-logo img { width: 124%; height: 124%; object-fit: contain; }

/* Row 2: 3 mini cells — Tutar / USD / Delta */
.dsp-ocard-cells {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 6px;
}
.dsp-ocard-cell {
  background: ${COLOR.bg};
  border: 1px solid ${COLOR.divider};
  border-radius: 7px;
  padding: 6px 10px;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  min-width: 0;
}
.dsp-ocard-cell-lbl {
  font-size: 10px;
  text-transform: uppercase;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.textMuted};
  letter-spacing: 0.05em;
  flex-shrink: 0;
}
.dsp-ocard-cell-val {
  font-family: ${FONT.mono};
  font-size: 13px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
  text-align: right;
  line-height: 1.2;
}

/* Row 3: exits TP/SL/FS/FS-P inline */
.dsp-ocard-exits {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr 1fr;
  gap: 6px;
}
.dsp-ocard-exit {
  background: ${COLOR.bg};
  border: 1px solid ${COLOR.divider};
  border-radius: 7px;
  padding: 6px 9px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 5px;
  min-width: 0;
  font-family: ${FONT.mono};
  font-size: 13px;
}
.dsp-ocard-exit-lbl {
  font-size: 10px;
  text-transform: uppercase;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.textMuted};
  letter-spacing: 0.05em;
}
.dsp-ocard-exit-val { font-weight: ${FONT.weight.bold}; }
.dsp-ocard-exit.tp   .dsp-ocard-exit-val { color: ${COLOR.green}; }
.dsp-ocard-exit.sl   .dsp-ocard-exit-val { color: ${COLOR.red}; }
.dsp-ocard-exit.fs   .dsp-ocard-exit-val { color: ${COLOR.yellow}; }
.dsp-ocard-exit.fsp  .dsp-ocard-exit-val { color: ${COLOR.red}; }

/* Row 4: activity + sell button */
.dsp-ocard-sell {
  background: ${COLOR.redSoft};
  border: 1px solid ${COLOR.redSoft};
  color: ${COLOR.red};
  font-family: ${FONT.sans};
  font-size: 11px;
  font-weight: ${FONT.weight.bold};
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 6px 14px;
  border-radius: 7px;
  cursor: pointer;
  line-height: 1.1;
  flex-shrink: 0;
}
.dsp-ocard-sell.disabled {
  background: rgba(126,126,146,0.16);
  border-color: rgba(126,126,146,0.16);
  color: ${COLOR.textMuted};
  cursor: not-allowed;
}
`
);

function deriveStatus(text: string | null | undefined): string {
  const t = text ?? '';
  if (/Emir doldu/i.test(t)) return 'YENİ';
  if (/TP @|kapatma emri/i.test(t)) return 'TP HIT';
  if (/SL tetik|satış emri/i.test(t)) return 'SL HIT';
  if (/Force sell.*saniye|FS countdown/i.test(t)) return 'FS…';
  if (/FS @|ile kapandı/i.test(t)) return 'KAPANDI';
  if (/TP yakla/i.test(t)) return 'TP YKN';
  if (/SL yakla/i.test(t)) return 'SL YKN';
  if (/Claim/i.test(t)) return 'CLAIM';
  return '—';
}

type SellState = 'active' | 'closing' | 'closed' | 'pending';
function deriveSellState(t: string | null | undefined): SellState {
  const x = t ?? '';
  if (/ile kapandı|kapandı$/i.test(x)) return 'closed';
  if (/TP @|SL tetik|FS @|kapatma emri|satış emri/i.test(x)) return 'closing';
  if (/dolum bekleniyor|gönderiliyor/i.test(x)) return 'pending';
  return 'active';
}
function sellLabel(s: SellState): string {
  if (s === 'closed') return 'KAPANDI';
  if (s === 'closing') return 'KAPANIYOR';
  if (s === 'pending') return 'BEKLİYOR';
  return 'ŞİMDİ SAT';
}

function OpenCard({ position }: { position: PositionSummary }) {
  const coin = COIN_FALLBACK[position.asset ?? ''];
  const tone = position.pnl_tone ?? 'neutral';
  const pnlFg = PNL_TONE[tone]?.fg ?? COLOR.text;
  const live = position.live;
  const status = deriveStatus(position.activity?.text);
  const side = live?.side ?? position.side ?? 'UP';
  const sideColor = side === 'UP' ? COLOR.green : COLOR.red;
  const coinTone = coin?.tone;
  const bgStyle = coinTone
    ? { background: `linear-gradient(135deg, ${coinTone}1f 0%, ${COLOR.surface} 55%)`, borderColor: `${coinTone}55` }
    : undefined;
  const cost = position.requested_amount_usd != null ? `$${position.requested_amount_usd.toFixed(2)}` : '—';
  const exits = position.exits;
  const sellState = deriveSellState(position.activity?.text);
  const sellDisabled = sellState !== 'active';

  return (
    <div className={`dsp-ocard tone-${tone}`} style={bgStyle}>
      <div className="dsp-ocard-logo">
        {coin?.logo_url ? <img src={coin.logo_url} alt={position.asset ?? ''} /> : null}
      </div>

      <div className="dsp-ocard-id">
        <div className="dsp-ocard-id-row">
          <span className="dsp-ocard-ticker">{position.asset}</span>
        </div>
        <span className="dsp-ocard-status">{status}</span>
      </div>

      <div className="dsp-ocard-pnl">
        <span className="dsp-ocard-pct" style={{ color: pnlFg }}>
          {position.pnl_big ?? '—'}
        </span>
        <span className="dsp-ocard-usd" style={{ color: pnlFg }}>
          {position.pnl_amount ?? ''}
        </span>
      </div>

      <div className="dsp-ocard-cells">
        <div className="dsp-ocard-cell">
          <span className="dsp-ocard-cell-lbl">Tutar</span>
          <span className="dsp-ocard-cell-val" style={{ color: COLOR.cyan }}>{cost}</span>
        </div>
        <div className="dsp-ocard-cell">
          <span className="dsp-ocard-cell-lbl">Giriş</span>
          <span className="dsp-ocard-cell-val" style={{ color: sideColor }}>
            {live?.entry ?? '—'}
          </span>
        </div>
        <div className="dsp-ocard-cell">
          <span className="dsp-ocard-cell-lbl">Canlı</span>
          <span className="dsp-ocard-cell-val">{live?.live ?? '—'}</span>
        </div>
        <div className="dsp-ocard-cell">
          <span className="dsp-ocard-cell-lbl">Δ</span>
          <span className="dsp-ocard-cell-val" style={{ color: signColor(live?.delta_text) }}>
            {live?.delta_text ?? '—'}
          </span>
        </div>
      </div>

      <div className="dsp-ocard-bottom">
        {exits && (
          <>
            <div className="dsp-ocard-exit tp">
              <span className="dsp-ocard-exit-lbl">TP</span>
              <span className="dsp-ocard-exit-val">{exits.tp}</span>
            </div>
            <div className="dsp-ocard-exit sl">
              <span className="dsp-ocard-exit-lbl">SL</span>
              <span className="dsp-ocard-exit-val">{exits.sl}</span>
            </div>
            <div className="dsp-ocard-exit fs">
              <span className="dsp-ocard-exit-lbl">FS</span>
              <span className="dsp-ocard-exit-val">{exits.fs}</span>
            </div>
          </>
        )}
        <button
          type="button"
          className={`dsp-ocard-sell${sellDisabled ? ' disabled' : ''}`}
          disabled={sellDisabled}
        >
          {sellLabel(sellState)}
        </button>
      </div>
    </div>
  );
}

function signColor(raw: string | null | undefined): string | undefined {
  if (!raw) return undefined;
  const m = raw.match(/(-?\d+(?:\.\d+)?)/);
  if (!m) return undefined;
  const n = parseFloat(m[1]);
  if (n > 0) return COLOR.green;
  if (n < 0) return COLOR.red;
  return COLOR.textMuted;
}

export default function OpenRail({ positions }: { positions: PositionSummary[] }) {
  const openOnly = positions.filter((p) => p.variant !== 'claim');
  return (
    <aside className="dsp-orail">
      <div className="dsp-orail-list">
        {openOnly.map((p) => (
          <OpenCard key={p.position_id} position={p} />
        ))}
      </div>
    </aside>
  );
}
