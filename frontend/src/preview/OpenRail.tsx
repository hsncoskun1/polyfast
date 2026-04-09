/**
 * OpenRail — açık işlemler sağ yan panelde dikey kart listesi.
 * NotifRail ile aynı kart iskeleti; ama pozisyon bilgisi: coin + yön + PnL +
 * giriş + canlı + kısa durum.
 */

import { COLOR, FONT, SIZE, PNL_TONE, ensureStyles } from './styles';
import { COIN_FALLBACK } from './coinRegistry';
import type { PositionSummary, ClaimSummary } from '../api/dashboard';

ensureStyles(
  'openrail-v45',
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
  grid-template-columns: 1fr auto;
  grid-template-rows: auto auto auto;
  column-gap: 10px;
  row-gap: 2px;
  min-width: 0;
  overflow: hidden;
  transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
}
.dsp-ocard:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(6, 182, 212, 0.18);
  border-color: ${COLOR.cyan};
}

.dsp-ocard-logo {
  width: 32px; height: 32px;
  border-radius: 50%;
  background: ${COLOR.bg};
  display: flex; align-items: center; justify-content: center;
  overflow: hidden;
  flex-shrink: 0;
}
.dsp-ocard-id {
  grid-column: 1;
  grid-row: 1;
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-rows: auto auto auto;
  column-gap: 10px;
  row-gap: 3px;
  min-width: 0;
  align-content: start;
}
.dsp-ocard-id > .dsp-ocard-logo { grid-column: 1; grid-row: 1 / span 3; align-self: center; }
.dsp-ocard-id-row { grid-column: 2; grid-row: 1; line-height: 1.1; }
.dsp-ocard-id-lbl { grid-column: 2; grid-row: 2; line-height: 1.1; margin-top: 1px; }
.dsp-ocard-id-val { grid-column: 2; grid-row: 3; line-height: 1.1; }
.dsp-ocard-id-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.dsp-ocard-id-lbl {
  font-size: 11px;
  text-transform: uppercase;
  font-weight: ${FONT.weight.bold};
  letter-spacing: 0.06em;
  color: ${COLOR.textMuted};
}
.dsp-ocard-id-val {
  font-family: ${FONT.mono};
  font-size: 17px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.cyan};
}
.dsp-ocard-sell-slot {
  grid-column: 2;
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
.dsp-ocard-ticker:hover { color: ${COLOR.cyan}; text-decoration: underline; text-decoration-color: ${COLOR.cyan}; text-underline-offset: 4px; }
.dsp-ocard-ticker:hover .dsp-ocard-ticker-ico { opacity: 1; }
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
  grid-column: 2;
  grid-row: 1;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  align-items: flex-end;
  gap: 3px;
  min-width: 0;
}
.dsp-ocard-pct {
  font-family: ${FONT.mono};
  font-size: 24px;
  font-weight: ${FONT.weight.bold};
  line-height: 1.05;
  letter-spacing: -0.02em;
}
.dsp-ocard-usd {
  font-family: ${FONT.mono};
  font-size: 13px;
  font-weight: ${FONT.weight.bold};
  text-transform: uppercase;
  letter-spacing: 0.04em;
  line-height: 1.1;
}

/* Row 2 (span 3): info cells — Tutar / Giriş / Canlı / Delta */
.dsp-ocard-cells {
  grid-column: 1 / -1;
  grid-row: 2;
  margin-top: 4px;
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 4px;
}

/* Row 3 (span 3): exits + sell */
.dsp-ocard-bottom {
  grid-column: 1 / -1;
  grid-row: 3;
  margin-top: 6px;
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
.dsp-ocard-icbtn:focus-visible { outline: 2px solid ${COLOR.cyan}; outline-offset: 2px; }
.dsp-ocard-sell:focus-visible { outline: 2px solid ${COLOR.cyan}; outline-offset: 2px; }
.dsp-ocard-ticker:focus-visible { outline: 2px solid ${COLOR.cyan}; outline-offset: 2px; border-radius: 3px; }
.dsp-ocard.tone-profit { border-left-color: ${COLOR.green}; }
.dsp-ocard.tone-loss   { border-left-color: ${COLOR.red}; }
.dsp-ocard.tone-neutral,
.dsp-ocard.tone-off    { border-left-color: ${COLOR.divider}; }
.dsp-ocard.tone-pending { border-left-color: ${COLOR.yellow}; }

.dsp-ocard-logo img { width: 124%; height: 124%; object-fit: contain; }
.dsp-ocard-link { display: inline-flex; text-decoration: none; cursor: pointer; }
.dsp-ocard-link:hover .dsp-ocard-logo { filter: brightness(1.15); }
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
  font-size: 13px;
  text-transform: uppercase;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.textMuted};
  letter-spacing: 0.05em;
  flex-shrink: 0;
}
.dsp-ocard-cell-val {
  font-family: ${FONT.mono};
  font-size: 17px;
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
  padding: 11px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  min-width: 0;
  font-family: ${FONT.mono};
  font-size: 17px;
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
  font-size: 13px;
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
  background: rgba(126, 126, 146, 0.08);
  border-color: ${COLOR.divider};
  color: ${COLOR.textDim};
  cursor: not-allowed;
  opacity: 0.4;
}

/* Claim variant — OpenCard iskeleti, sarı sol border */
.dsp-ocard.claim { border-left-color: ${COLOR.yellow}; }
.dsp-ocard.claim:hover { box-shadow: 0 4px 14px rgba(234, 179, 8, 0.18); border-color: ${COLOR.yellow}; }
.dsp-ocard.claim .dsp-ocard-bottom { grid-template-columns: 1fr 1fr; }
/* Claim popover — deneme exit'ten yukarı, bottom row boyunca */
.dsp-ocard-claim-pop {
  position: absolute;
  left: 0;
  right: calc(-100% - 6px);
  bottom: calc(100% + 4px);
  padding: 6px 10px;
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
.dsp-ocard-claim-pop.fail {
  background: ${COLOR.red};
  border: 1px solid ${COLOR.red};
  color: #fff;
}
.dsp-ocard-claim-pop.retry {
  background: ${COLOR.yellow};
  border: 1px solid ${COLOR.yellow};
  color: #1a1505;
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
  if (/TP @|SL tetik|FS @|FS eşik|zorunlu kapatma|kapatma emri|satış emri/i.test(x)) return 'closing';
  if (/dolum bekleniyor|gönderiliyor/i.test(x)) return 'pending';
  return 'active';
}
function sellLabel(_s: SellState): string {
  return 'SAT';
}
function sellTitle(s: SellState): string {
  if (s === 'closed')  return 'Pozisyon zaten kapandı';
  if (s === 'closing') return 'Kapanış emri yolda — manuel satış mümkün değil';
  if (s === 'pending') return 'Dolum bekleniyor — henüz açık pozisyon yok';
  return 'Pozisyonu manuel olarak sat (Market FOK)';
}

function OpenCard({ position }: { position: PositionSummary }) {
  const coin = COIN_FALLBACK[position.asset ?? ''];
  const tone = position.pnl_tone ?? 'neutral';
  const pnlFg = PNL_TONE[tone]?.fg ?? COLOR.text;
  const live = position.live;
  const actives = deriveActiveExits(position.activity?.text);
  const actText = position.activity?.text ?? '';
  // Popover tek yerde render — öncelik sırasına göre ilk active hücre
  const primary: ExitKey | null = (['tp','sl','fsp','fs'] as ExitKey[]).find((k) => actives.has(k)) ?? null;
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
      <div className="dsp-ocard-id">
        <a
          className="dsp-ocard-link"
          href={position.event_url ?? '#'}
          target="_blank"
          rel="noopener noreferrer"
          title={`${position.asset} Polymarket event'i aç`}
        >
          <div className="dsp-ocard-logo">
            {coin?.logo_url ? <img src={coin.logo_url} alt={position.asset ?? ''} /> : null}
          </div>
        </a>
        <div className="dsp-ocard-id-row">
          <a
            className="dsp-ocard-ticker"
            href={position.event_url ?? '#'}
            target="_blank"
            rel="noopener noreferrer"
            title={`${position.asset} Polymarket event'i aç`}
          >
            <span>{position.asset}</span>
            <span className="dsp-ocard-ticker-ico" aria-hidden>🔗</span>
          </a>
          <button
            type="button"
            className="dsp-ocard-icbtn dollar"
            title="Pozisyon aktif — kapatmak için SAT"
            aria-label="Aktif"
            onClick={() => window.alert(`${position.asset} zaten aktif. Kapatmak için SAT butonunu kullan.`)}
          >$</button>
          <button
            type="button"
            className="dsp-ocard-icbtn"
            title="Coin ayarları (yakında)"
            aria-label="Ayarlar"
            onClick={() => window.alert(`${position.asset} ayarları — modal Phase 2'de eklenecek`)}
          >⚙</button>
        </div>
        <div className="dsp-ocard-id-lbl">Tutar</div>
        <div className="dsp-ocard-id-val">{cost}</div>
      </div>

      <div className="dsp-ocard-pnl">
        <span className="dsp-ocard-pct" style={{ color: pnlFg }}>
          {position.pnl_big ?? '—'}
        </span>
        <span className="dsp-ocard-usd" style={{ color: pnlFg }}>
          {position.pnl_amount ?? ''}
        </span>
        <button
          type="button"
          className={`dsp-ocard-sell${sellDisabled ? ' disabled' : ''}`}
          disabled={sellDisabled}
          title={sellTitle(sellState)}
          onClick={() => {
            // Direkt satış — confirm yok, Phase 2'de backend wiring
            // eslint-disable-next-line no-console
            console.log(`[preview] Market FOK sell → ${position.asset}`);
          }}
        >
          {sellLabel(sellState)}
        </button>
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
          <span className="dsp-ocard-cell-val" style={{ color: sideColor }}>
            {side === 'UP' ? '▲' : '▼'} {live?.live ?? '—'}
          </span>
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

export default function OpenRail({
  positions,
  claims,
}: {
  positions: PositionSummary[];
  claims?: ClaimSummary[];
}) {
  const claimPositions = positions.filter((p) => p.variant === 'claim');
  const openOnly = positions.filter((p) => p.variant !== 'claim');
  const claimByPos = new Map<string, ClaimSummary>();
  (claims ?? []).forEach((c) => claimByPos.set(c.position_id, c));
  return (
    <aside className="dsp-orail">
      <div className="dsp-orail-list">
        {claimPositions.map((p) => (
          <ClaimCard
            key={p.position_id}
            position={p}
            claim={claimByPos.get(p.position_id) ?? null}
          />
        ))}
        {openOnly.map((p) => (
          <OpenCard key={p.position_id} position={p} />
        ))}
      </div>
    </aside>
  );
}

/* ═══ ClaimCard — OpenCard ile aynı tasarım dili ═══════════════ */
function ClaimCard({
  position,
  claim,
}: {
  position: PositionSummary;
  claim: ClaimSummary | null;
}) {
  const coin = COIN_FALLBACK[position.asset ?? ''];
  const coinTone = coin?.tone;
  const bgStyle = coinTone
    ? { background: `linear-gradient(135deg, ${coinTone}1f 0%, ${COLOR.surface} 55%)` }
    : undefined;

  const status = claim?.status ?? 'RETRY';
  const toneColor =
    status === 'OK'   ? COLOR.green :
    status === 'FAIL' ? COLOR.red :
    COLOR.yellow;
  const label =
    status === 'OK'   ? 'CLAIM BAŞARILI' :
    status === 'FAIL' ? 'MAX DENEME' :
    'CLAIM BEKLİYOR';

  const retryText = claim
    ? `${claim.retry ?? claim.retry_count ?? 0}/${claim.max_retry ?? 20}`
    : '—';
  const nextText = claim?.next_sec != null ? `${claim.next_sec}s` : '—';
  const payout = claim?.payout ?? (status === 'OK' ? position.pnl_amount ?? '—' : '—');
  const costRaw = position.requested_amount_usd != null
    ? `$${position.requested_amount_usd.toFixed(2)}`
    : '—';

  return (
    <div className="dsp-ocard claim" style={bgStyle}>
      <div className="dsp-ocard-id">
        <a
          className="dsp-ocard-link"
          href={position.event_url ?? '#'}
          target="_blank"
          rel="noopener noreferrer"
          title={`${position.asset} Polymarket event'i aç`}
        >
          <div className="dsp-ocard-logo">
            {coin?.logo_url ? <img src={coin.logo_url} alt={position.asset ?? ''} /> : null}
          </div>
        </a>
        <div className="dsp-ocard-id-row">
          <a
            className="dsp-ocard-ticker"
            href={position.event_url ?? '#'}
            target="_blank"
            rel="noopener noreferrer"
            title={`${position.asset} Polymarket event'i aç`}
          >
            <span>{position.asset}</span>
            <span className="dsp-ocard-ticker-ico" aria-hidden>🔗</span>
          </a>
        </div>
        <div className="dsp-ocard-id-lbl">Tutar</div>
        <div className="dsp-ocard-id-val">{costRaw}</div>
      </div>

      <div className="dsp-ocard-pnl">
        <span className="dsp-ocard-pct" style={{ color: toneColor }}>
          {label}
        </span>
        <span className="dsp-ocard-usd" style={{ color: toneColor }}>
          {payout}
        </span>
      </div>

      <div className="dsp-ocard-bottom">
        <div
          className="dsp-ocard-exit"
          style={
            status === 'FAIL'
              ? { position: 'relative', background: COLOR.redSoft, borderColor: COLOR.red }
              : status === 'RETRY'
                ? { position: 'relative', background: COLOR.yellowSoft, borderColor: COLOR.yellow }
                : undefined
          }
        >
          <span className="dsp-ocard-exit-lbl">Deneme</span>
          <span className="dsp-ocard-exit-val" style={{ color: toneColor }}>{retryText}</span>
          {status === 'FAIL' && (
            <div className="dsp-ocard-claim-pop fail">Max deneme | elle claim yapınız</div>
          )}
          {status === 'RETRY' && (
            <div className="dsp-ocard-claim-pop retry">{`Deneme ${retryText} | ${nextText} sonra tekrar`}</div>
          )}
        </div>
        <div className="dsp-ocard-exit sl">
          <span className="dsp-ocard-exit-lbl">Sonraki</span>
          <span className="dsp-ocard-exit-val">{nextText}</span>
        </div>
      </div>
    </div>
  );
}
