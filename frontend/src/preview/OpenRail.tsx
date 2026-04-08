/**
 * OpenRail — açık işlemler sağ yan panelde dikey kart listesi.
 * NotifRail ile aynı kart iskeleti; ama pozisyon bilgisi: coin + yön + PnL +
 * giriş + canlı + kısa durum.
 */

import { COLOR, FONT, SIZE, PNL_TONE, ensureStyles } from './styles';
import { COIN_FALLBACK } from './coinRegistry';
import type { PositionSummary } from '../api/dashboard';

ensureStyles(
  'openrail-v1',
  `
.dsp-orail {
  width: 280px;
  flex-shrink: 0;
  background: ${COLOR.bg};
  border-left: 1px solid ${COLOR.border};
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.dsp-orail-hdr {
  padding: 12px 14px 10px;
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
  padding: 10px 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* Kart — 3 micro-row: header (logo+ticker+durum), money (pnl%+usd), prices (giriş/canlı/delta) */
.dsp-ocard {
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  border-left-width: 3px;
  border-radius: ${SIZE.radius}px;
  padding: 8px 10px 9px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}
.dsp-ocard.tone-profit { border-left-color: ${COLOR.green}; }
.dsp-ocard.tone-loss   { border-left-color: ${COLOR.red}; }
.dsp-ocard.tone-neutral,
.dsp-ocard.tone-off    { border-left-color: ${COLOR.divider}; }
.dsp-ocard.tone-pending { border-left-color: ${COLOR.yellow}; }

.dsp-ocard-row {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}
.dsp-ocard-logo {
  width: 20px; height: 20px;
  border-radius: 50%;
  background: ${COLOR.bg};
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  overflow: hidden;
}
.dsp-ocard-logo img { width: 124%; height: 124%; object-fit: contain; }
.dsp-ocard-ticker {
  font-size: 12px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
  letter-spacing: 0.03em;
}
.dsp-ocard-side {
  font-family: ${FONT.mono};
  font-size: 11px;
  font-weight: ${FONT.weight.bold};
}
.dsp-ocard-status {
  margin-left: auto;
  font-family: ${FONT.mono};
  font-size: 9px;
  font-weight: ${FONT.weight.bold};
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 2px 6px;
  border-radius: 8px;
  border: 1px solid ${COLOR.divider};
  color: ${COLOR.textMuted};
}

.dsp-ocard-money {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.dsp-ocard-pct {
  font-family: ${FONT.mono};
  font-size: 15px;
  font-weight: ${FONT.weight.bold};
}
.dsp-ocard-usd {
  font-family: ${FONT.mono};
  font-size: 11px;
  color: ${COLOR.textMuted};
}

.dsp-ocard-prices {
  display: flex;
  justify-content: space-between;
  gap: 6px;
  font-family: ${FONT.mono};
  font-size: 10px;
  color: ${COLOR.textMuted};
}
.dsp-ocard-prices > span strong {
  color: ${COLOR.text};
  font-weight: ${FONT.weight.bold};
  margin-left: 2px;
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

function OpenCard({ position }: { position: PositionSummary }) {
  const coin = COIN_FALLBACK[position.asset ?? ''];
  const tone = position.pnl_tone ?? 'neutral';
  const pnlFg = PNL_TONE[tone]?.fg ?? COLOR.text;
  const live = position.live;
  const status = deriveStatus(position.activity?.text);
  const side = live?.side ?? position.side ?? 'UP';
  const sideColor = side === 'UP' ? COLOR.green : COLOR.red;
  return (
    <div className={`dsp-ocard tone-${tone}`}>
      <div className="dsp-ocard-row">
        <div className="dsp-ocard-logo">
          {coin?.logo_url ? <img src={coin.logo_url} alt={position.asset ?? ''} /> : null}
        </div>
        <span className="dsp-ocard-ticker">{position.asset}</span>
        <span className="dsp-ocard-side" style={{ color: sideColor }}>
          {side === 'UP' ? '▲' : '▼'} {live?.entry ?? '—'}
        </span>
        <span className="dsp-ocard-status">{status}</span>
      </div>
      <div className="dsp-ocard-money">
        <span className="dsp-ocard-pct" style={{ color: pnlFg }}>
          {position.pnl_big ?? '—'}
        </span>
        <span className="dsp-ocard-usd" style={{ color: pnlFg }}>
          {position.pnl_amount ?? ''}
        </span>
      </div>
      <div className="dsp-ocard-prices">
        <span>Canlı<strong>{live?.live ?? '—'}</strong></span>
        <span>Δ<strong>{live?.delta_text ?? '—'}</strong></span>
      </div>
    </div>
  );
}

export default function OpenRail({ positions }: { positions: PositionSummary[] }) {
  const openOnly = positions.filter((p) => p.variant !== 'claim');
  return (
    <aside className="dsp-orail">
      <div className="dsp-orail-hdr">
        <span className="dsp-orail-hdr-title">Açık İşlemler</span>
        <span className="dsp-orail-hdr-badge">{openOnly.length}</span>
      </div>
      <div className="dsp-orail-list">
        {openOnly.map((p) => (
          <OpenCard key={p.position_id} position={p} />
        ))}
      </div>
    </aside>
  );
}
