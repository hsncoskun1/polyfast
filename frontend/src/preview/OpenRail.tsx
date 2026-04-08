/**
 * OpenRail — açık işlemler sağ yan panelde dikey kart listesi.
 * NotifRail ile aynı kart iskeleti; ama pozisyon bilgisi: coin + yön + PnL +
 * giriş + canlı + kısa durum.
 */

import { COLOR, FONT, SIZE, PNL_TONE, ensureStyles } from './styles';
import { COIN_FALLBACK } from './coinRegistry';
import type { PositionSummary } from '../api/dashboard';

ensureStyles(
  'openrail-v27',
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
  padding: 10px 12px;
  display: grid;
  grid-template-columns: auto 1fr auto;
  grid-template-rows: auto auto auto auto;
  column-gap: 10px;
  row-gap: 2px;
  min-width: 0;
  overflow: hidden;
}

.dsp-ocard-logo {
  grid-column: 1;
  grid-row: 1 / span 2;
  align-self: center;
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
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.dsp-ocard-id-bottom {
  grid-column: 2;
  grid-row: 2;
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-family: ${FONT.mono};
  font-size: 12px;
  color: ${COLOR.textMuted};
}
.dsp-ocard-sell-slot {
  grid-column: 3;
  grid-row: 2;
  display: flex;
  justify-content: flex-end;
  align-items: center;
}
.dsp-ocard-id-bottom strong {
  color: ${COLOR.cyan};
  font-weight: ${FONT.weight.bold};
  font-size: 13px;
}
.dsp-ocard-ticker {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 20px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
  letter-spacing: 0.02em;
  text-decoration: none;
  cursor: pointer;
}
.dsp-ocard-ticker:hover { color: ${COLOR.cyan}; }
.dsp-ocard-ticker-ico {
  font-size: 13px;
  opacity: 0.75;
  line-height: 1;
}
.dsp-ocard-side {
  font-family: ${FONT.mono};
  font-size: 13px;
  font-weight: ${FONT.weight.bold};
}

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
  grid-row: 3;
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 4px;
}

/* Row 3 (span 3): exits + sell */
.dsp-ocard-bottom {
  grid-column: 1 / -1;
  grid-row: 4;
  display: grid;
  grid-template-columns: 1fr 1fr 1fr 1fr;
  gap: 4px;
  align-items: center;
}
.dsp-ocard-icbtn {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  border: none;
  background: ${COLOR.yellowSoft};
  color: ${COLOR.yellow};
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 13px;
  font-weight: ${FONT.weight.bold};
  flex-shrink: 0;
  font-family: ${FONT.sans};
  line-height: 1;
  padding: 0;
}
.dsp-ocard-icbtn.dollar {
  background: ${COLOR.greenSoft};
  color: ${COLOR.green};
}
.dsp-ocard-icbtn:hover { filter: brightness(1.25); }
.dsp-ocard.tone-profit { border-left-color: ${COLOR.green}; }
.dsp-ocard.tone-loss   { border-left-color: ${COLOR.red}; }
.dsp-ocard.tone-neutral,
.dsp-ocard.tone-off    { border-left-color: ${COLOR.divider}; }
.dsp-ocard.tone-pending { border-left-color: ${COLOR.yellow}; }

.dsp-ocard-logo img { width: 124%; height: 124%; object-fit: contain; }
.dsp-ocard-cell {
  background: ${COLOR.bg};
  border: 1px solid ${COLOR.divider};
  border-radius: 6px;
  padding: 4px 7px;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
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
.dsp-ocard-exit {
  position: relative;
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
/* Aktif (tetiklenen) exit hücresi — kendi toneunda bg */
.dsp-ocard-exit.active.tp  { background: ${COLOR.greenSoft};  border-color: ${COLOR.green}; }
.dsp-ocard-exit.active.sl  { background: ${COLOR.redSoft};    border-color: ${COLOR.red}; }
.dsp-ocard-exit.active.fs  { background: ${COLOR.yellowSoft}; border-color: ${COLOR.yellow}; }
.dsp-ocard-exit.active.fsp { background: ${COLOR.yellowSoft}; border-color: ${COLOR.yellow}; }

/* Popover — aktif exit'in üzerinden yukarı açılan bildirim (cells row genişliğinde) */
.dsp-ocard-exit-pop {
  position: absolute;
  bottom: calc(100% + 4px);
  padding: 6px 10px;
  border: 1px solid;
  border-radius: 7px 7px 0 0;
  font-family: ${FONT.sans};
  font-size: 12px;
  font-weight: ${FONT.weight.bold};
  line-height: 1.25;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  z-index: 3;
  transform-origin: bottom center;
  animation: dsp-ocard-pop 3s cubic-bezier(0.2, 0.8, 0.25, 1) infinite;
  box-shadow: 0 -3px 14px rgba(0,0,0,0.35);
}
/* TP cell 1. slot → 4 col span - cell's own slot = 3 slot sağa. Margin-based full-width. */
.dsp-ocard-bottom .dsp-ocard-exit.active .dsp-ocard-exit-pop {
  left: 0;
  right: 0;
}
/* TP (col 1): sağa 3 col genişle */
.dsp-ocard-exit.tp.active .dsp-ocard-exit-pop { right: calc(-300% - 12px); }
/* SL (col 2): 1 col sola + 2 col sağa */
.dsp-ocard-exit.sl.active .dsp-ocard-exit-pop { left: calc(-100% - 4px); right: calc(-200% - 8px); }
/* FS (col 3): 2 col sola + 1 col sağa */
.dsp-ocard-exit.fs.active .dsp-ocard-exit-pop { left: calc(-200% - 8px); right: calc(-100% - 4px); }
/* FSP (col 4): 3 col sola */
.dsp-ocard-exit.fsp.active .dsp-ocard-exit-pop { left: calc(-300% - 12px); right: 0; }
.dsp-ocard-exit.active.tp  .dsp-ocard-exit-pop { background: ${COLOR.green};  border-color: ${COLOR.green};  color: #0b1e10; }
.dsp-ocard-exit.active.sl  .dsp-ocard-exit-pop { background: ${COLOR.red};    border-color: ${COLOR.red};    color: #fff; }
.dsp-ocard-exit.active.fs  .dsp-ocard-exit-pop { background: ${COLOR.yellow}; border-color: ${COLOR.yellow}; color: #1a1505; }
.dsp-ocard-exit.active.fsp .dsp-ocard-exit-pop { background: ${COLOR.yellow}; border-color: ${COLOR.yellow}; color: #1a1505; }
.dsp-ocard-exit-pop::after {
  content: '';
  position: absolute;
  left: 50%;
  bottom: -4px;
  transform: translateX(-50%);
  width: 0;
  height: 0;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-top: 5px solid;
  border-top-color: inherit;
}
@keyframes dsp-ocard-pop {
  0%   { transform: translateY(8px) scaleY(0); opacity: 0; }
  18%  { transform: translateY(-2px) scaleY(1.06); opacity: 1; }
  25%  { transform: translateY(0) scaleY(1); opacity: 1; }
  82%  { transform: translateY(0) scaleY(1); opacity: 1; }
  100% { transform: translateY(8px) scaleY(0); opacity: 0; }
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
.dsp-ocard-exit.fsp  .dsp-ocard-exit-val { color: ${COLOR.yellow}; }

/* Row 4: activity + sell button */
.dsp-ocard-sell {
  background: ${COLOR.redSoft};
  border: 1px solid ${COLOR.redSoft};
  color: ${COLOR.red};
  font-family: ${FONT.sans};
  font-size: 12px;
  font-weight: ${FONT.weight.bold};
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 5px 12px;
  border-radius: 7px;
  cursor: pointer;
  line-height: 1.1;
  flex-shrink: 0;
}
.dsp-ocard-sell.disabled {
  background: rgba(239, 68, 68, 0.08);
  border-color: rgba(239, 68, 68, 0.08);
  color: rgba(239, 68, 68, 0.45);
  cursor: not-allowed;
  opacity: 0.55;
}
`
);

type ExitKey = 'tp' | 'sl' | 'fs' | 'fsp';
function deriveActiveExits(text: string | null | undefined): Set<ExitKey> {
  const t = text ?? '';
  const s = new Set<ExitKey>();
  if (/TP @|TP tetik|kapatma emri|TP yakla/i.test(t)) s.add('tp');
  if (/SL tetik|SL yakla|SL @/i.test(t)) s.add('sl');
  if (/Force sell|FS @|FS countdown|Force sell ile/i.test(t)) s.add('fs');
  if (/FS eşik|F\/P tetik|FS p&l|FS pnl/i.test(t)) s.add('fsp');
  return s;
}

type SellState = 'active' | 'closing' | 'closed' | 'pending';
function deriveSellState(t: string | null | undefined): SellState {
  const x = t ?? '';
  if (/ile kapandı|kapandı$/i.test(x)) return 'closed';
  if (/TP @|SL tetik|FS @|kapatma emri|satış emri/i.test(x)) return 'closing';
  if (/dolum bekleniyor|gönderiliyor/i.test(x)) return 'pending';
  return 'active';
}
function sellLabel(_s: SellState): string {
  return 'SAT';
}

function OpenCard({ position }: { position: PositionSummary }) {
  const coin = COIN_FALLBACK[position.asset ?? ''];
  const tone = position.pnl_tone ?? 'neutral';
  const pnlFg = PNL_TONE[tone]?.fg ?? COLOR.text;
  const live = position.live;
  const actives = deriveActiveExits(position.activity?.text);
  const actText = position.activity?.text ?? '';
  // Popover tek yerde render — öncelik sırasına göre ilk active hücre
  const primary: ExitKey | null = (['tp','sl','fs','fsp'] as ExitKey[]).find((k) => actives.has(k)) ?? null;
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
        <a
          className="dsp-ocard-ticker"
          href={position.event_url ?? '#'}
          target="_blank"
          rel="noopener noreferrer"
          title={`${position.asset} Polymarket event'i aç`}
        >
          <span>{position.asset}</span>
          <span className="dsp-ocard-ticker-ico">↗</span>
        </a>
        <button type="button" className="dsp-ocard-icbtn dollar" title="Aktif" aria-label="Aktif">$</button>
        <button type="button" className="dsp-ocard-icbtn" title="Ayarlar" aria-label="Ayarlar">⚙</button>
      </div>

      <div className="dsp-ocard-id-bottom">
        <span>Tutar</span>
        <strong>{cost}</strong>
      </div>

      <div className="dsp-ocard-sell-slot">
        <button
          type="button"
          className={`dsp-ocard-sell${sellDisabled ? ' disabled' : ''}`}
          disabled={sellDisabled}
        >
          {sellLabel(sellState)}
        </button>
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
          <span className="dsp-ocard-cell-lbl">Giriş</span>
          <span className="dsp-ocard-cell-val" style={{ color: sideColor }}>
            {side === 'UP' ? '▲' : '▼'} {live?.entry ?? '—'}
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
            <div className={`dsp-ocard-exit tp${actives.has('tp') ? ' active' : ''}`}>
              <span className="dsp-ocard-exit-lbl">TP</span>
              <span className="dsp-ocard-exit-val">{exits.tp}</span>
              {primary === 'tp' && <div className="dsp-ocard-exit-pop">{actText}</div>}
            </div>
            <div className={`dsp-ocard-exit sl${actives.has('sl') ? ' active' : ''}`}>
              <span className="dsp-ocard-exit-lbl">SL</span>
              <span className="dsp-ocard-exit-val">{exits.sl}</span>
              {primary === 'sl' && <div className="dsp-ocard-exit-pop">{actText}</div>}
            </div>
            <div className={`dsp-ocard-exit fs${actives.has('fs') ? ' active' : ''}`}>
              <span className="dsp-ocard-exit-lbl">FS</span>
              <span className="dsp-ocard-exit-val">{exits.fs}</span>
              {primary === 'fs' && <div className="dsp-ocard-exit-pop">{actText}</div>}
            </div>
            <div className={`dsp-ocard-exit fsp${actives.has('fsp') ? ' active' : ''}`}>
              <span className="dsp-ocard-exit-lbl">F/P</span>
              <span className="dsp-ocard-exit-val">{exits.fs_pnl ?? '—'}</span>
              {primary === 'fsp' && <div className="dsp-ocard-exit-pop">{actText}</div>}
            </div>
          </>
        )}
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
