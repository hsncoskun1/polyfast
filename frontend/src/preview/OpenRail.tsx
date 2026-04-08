/**
 * OpenRail — açık işlemler sağ yan panelde dikey kart listesi.
 * NotifRail ile aynı kart iskeleti; ama pozisyon bilgisi: coin + yön + PnL +
 * giriş + canlı + kısa durum.
 */

import { COLOR, FONT, SIZE, PNL_TONE, ensureStyles } from './styles';
import { COIN_FALLBACK } from './coinRegistry';
import type { PositionSummary } from '../api/dashboard';

ensureStyles(
  'openrail-v8',
  `
.dsp-orail {
  width: 420px;
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
  overflow: hidden;
  padding: 6px 10px 8px;
  display: grid;
  grid-template-rows: repeat(6, 1fr);
  gap: 6px;
}

/* Kart — 3 micro-row: header (logo+ticker+durum), money (pnl%+usd), prices (giriş/canlı/delta) */
.dsp-ocard {
  flex: 1 1 0;
  min-height: 0;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  border-left-width: 3px;
  border-radius: ${SIZE.radius}px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 9px;
  min-width: 0;
  overflow: hidden;
}
.dsp-ocard.tone-profit { border-left-color: ${COLOR.green}; }
.dsp-ocard.tone-loss   { border-left-color: ${COLOR.red}; }
.dsp-ocard.tone-neutral,
.dsp-ocard.tone-off    { border-left-color: ${COLOR.divider}; }
.dsp-ocard.tone-pending { border-left-color: ${COLOR.yellow}; }

/* Row 1: logo + ticker + side + big pnl + status badge */
.dsp-ocard-hdr {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.dsp-ocard-logo {
  width: 30px; height: 30px;
  border-radius: 50%;
  background: ${COLOR.bg};
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  overflow: hidden;
}
.dsp-ocard-logo img { width: 124%; height: 124%; object-fit: contain; }
.dsp-ocard-ticker {
  font-size: 17px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
  letter-spacing: 0.02em;
}
.dsp-ocard-side {
  font-family: ${FONT.mono};
  font-size: 14px;
  font-weight: ${FONT.weight.bold};
}
.dsp-ocard-pct {
  margin-left: auto;
  font-family: ${FONT.mono};
  font-size: 19px;
  font-weight: ${FONT.weight.bold};
}
.dsp-ocard-status {
  font-family: ${FONT.mono};
  font-size: 9px;
  font-weight: ${FONT.weight.bold};
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 3px 7px;
  border-radius: 8px;
  border: 1px solid ${COLOR.divider};
  color: ${COLOR.textMuted};
  flex-shrink: 0;
}

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
  padding: 6px 9px;
  display: flex;
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
  text-align: right;
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
  padding: 6px 8px;
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
.dsp-ocard-footer {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  align-items: center;
}
.dsp-ocard-act {
  font-size: 12px;
  font-weight: ${FONT.weight.semibold};
  color: ${COLOR.textMuted};
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
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
      <div className="dsp-ocard-hdr">
        <div className="dsp-ocard-logo">
          {coin?.logo_url ? <img src={coin.logo_url} alt={position.asset ?? ''} /> : null}
        </div>
        <span className="dsp-ocard-ticker">{position.asset}</span>
        <span className="dsp-ocard-side" style={{ color: sideColor }}>
          {side === 'UP' ? '▲' : '▼'} {live?.entry ?? '—'}
        </span>
        <span className="dsp-ocard-pct" style={{ color: pnlFg }}>{position.pnl_big ?? '—'}</span>
        <span className="dsp-ocard-status">{status}</span>
      </div>

      <div className="dsp-ocard-cells">
        <div className="dsp-ocard-cell">
          <span className="dsp-ocard-cell-lbl">Tutar</span>
          <span className="dsp-ocard-cell-val" style={{ color: COLOR.cyan }}>{cost}</span>
        </div>
        <div className="dsp-ocard-cell">
          <span className="dsp-ocard-cell-lbl">USD</span>
          <span className="dsp-ocard-cell-val" style={{ color: pnlFg }}>{position.pnl_amount ?? '—'}</span>
        </div>
        <div className="dsp-ocard-cell">
          <span className="dsp-ocard-cell-lbl">Δ</span>
          <span className="dsp-ocard-cell-val">{live?.delta_text ?? '—'}</span>
        </div>
      </div>

      {exits && (
        <div className="dsp-ocard-exits">
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
          <div className="dsp-ocard-exit fsp">
            <span className="dsp-ocard-exit-lbl">F/P</span>
            <span className="dsp-ocard-exit-val">{exits.fs_pnl ?? '—'}</span>
          </div>
        </div>
      )}

      <div className="dsp-ocard-footer">
        <div className="dsp-ocard-act" title={position.activity?.text ?? ''}>
          {position.activity?.text ?? '—'}
        </div>
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

export default function OpenRail({ positions }: { positions: PositionSummary[] }) {
  const openOnly = positions.filter((p) => p.variant !== 'claim').slice(0, 6);
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
