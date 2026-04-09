/**
 * SearchRail — OpenRail kardeş paneli, "İşlem Aranan" tile'larını
 * OpenCard ile aynı grid yapısında gösterir.
 *
 *   [logo | ticker+$+⚙]        [Rule Pass hero] / [pnl_amount label] / [SAT]
 *   [    3-col cells (PTB / Canlı / Delta)           ]
 *   [    4-col rules (Zaman / Fiyat / Delta / Spread)]
 */

import { useMemo } from 'react';
import { COLOR, FONT, SIZE, ACTIVITY_TONE, ensureStyles } from './styles';
import { COIN_FALLBACK } from './coinRegistry';
import type { SearchTileContract, RuleSpecContract } from '../api/dashboard';

ensureStyles(
  'searchrail-v18',
  `
.dsp-srail-list {
  display: grid;
  grid-auto-rows: calc((100% - 18px) / 4);
  gap: 6px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-color: ${COLOR.cyan} transparent;
  scrollbar-width: thin;
}
.dsp-srail-list::-webkit-scrollbar { width: 8px; }
.dsp-srail-list::-webkit-scrollbar-track { background: transparent; }
.dsp-srail-list::-webkit-scrollbar-thumb { background: ${COLOR.cyan}; border-radius: 4px; }
.dsp-scard {
  min-height: 0;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  border-radius: ${SIZE.radius}px;
  padding: 7px 9px;
  transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
  display: grid;
  grid-template-columns: 1fr auto;
  grid-template-rows: auto auto auto auto;
  column-gap: 8px;
  row-gap: 2px;
  min-width: 0;
  overflow: hidden;
}
.dsp-scard:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(6, 182, 212, 0.18);
  border-color: ${COLOR.cyan};
}

/* Row 1 — id (logo + ticker + Tutar/Değer) */
.dsp-scard-id {
  grid-column: 1;
  grid-row: 1;
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-rows: auto auto;
  column-gap: 10px;
  row-gap: 3px;
  min-width: 0;
  align-content: start;
}
.dsp-scard-id > .dsp-scard-logo { grid-column: 1; grid-row: 1 / span 2; align-self: center; }
.dsp-scard-id-row { grid-column: 2; grid-row: 1; line-height: 1.1; display: flex; align-items: center; gap: 10px; }
.dsp-scard-id-val { grid-column: 2; grid-row: 2; line-height: 1.1; font-family: ${FONT.mono}; font-size: 15px; font-weight: ${FONT.weight.bold}; }

.dsp-scard-logo {
  width: 32px; height: 32px;
  border-radius: 50%;
  background: ${COLOR.bg};
  display: flex; align-items: center; justify-content: center;
  overflow: hidden;
  flex-shrink: 0;
}
.dsp-scard-logo img { width: 124%; height: 124%; object-fit: contain; }
.dsp-scard-link { display: inline-flex; text-decoration: none; cursor: pointer; }
.dsp-scard-link:hover .dsp-scard-logo { filter: brightness(1.15); }
.dsp-scard-icbtn:focus-visible,
.dsp-scard-ticker:focus-visible { outline: 2px solid ${COLOR.cyan}; outline-offset: 2px; border-radius: 4px; }

.dsp-scard-ticker {
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
.dsp-scard-ticker:hover { color: ${COLOR.cyan}; text-decoration: underline; text-decoration-color: ${COLOR.cyan}; text-underline-offset: 4px; }
.dsp-scard-ticker:hover .dsp-scard-ticker-ico { opacity: 1; }
.dsp-scard-ticker-ico { font-size: 13px; opacity: 0.75; line-height: 1; }

.dsp-scard-icbtn {
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
.dsp-scard-icbtn.dollar { background: ${COLOR.greenSoft}; color: ${COLOR.green}; }
.dsp-scard-icbtn:hover { filter: brightness(1.25); }
.dsp-scard-icbtn:focus-visible { outline: 2px solid ${COLOR.cyan}; outline-offset: 2px; }
.dsp-scard-ticker:focus-visible { outline: 2px solid ${COLOR.cyan}; outline-offset: 2px; border-radius: 3px; }

/* Row 1 col 2 — pnl hero (Rule pass 6/6) + status label */
.dsp-scard-pnl {
  grid-column: 2;
  grid-row: 1;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  align-items: flex-end;
  gap: 3px;
  min-width: 0;
}
.dsp-scard-pct {
  font-family: ${FONT.mono};
  font-size: 24px;
  font-weight: ${FONT.weight.bold};
  line-height: 1.05;
  letter-spacing: -0.02em;
}
.dsp-scard-usd {
  font-family: ${FONT.mono};
  font-size: 13px;
  font-weight: ${FONT.weight.bold};
  text-transform: uppercase;
  letter-spacing: 0.04em;
  line-height: 1.1;
}

/* Row 2 — cells (PTB / Canlı / Delta) */
.dsp-scard-cells {
  grid-column: 1 / -1;
  grid-row: 2;
  margin-top: 4px;
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 4px;
}
.dsp-scard-cell {
  background: ${COLOR.bg};
  border: 1px solid ${COLOR.divider};
  border-radius: 7px;
  padding: 6px 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  min-width: 0;
}
.dsp-scard-cell-lbl {
  font-size: 13px;
  text-transform: uppercase;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.textMuted};
  letter-spacing: 0.05em;
  flex-shrink: 0;
}
.dsp-scard-cell-val {
  font-family: ${FONT.mono};
  font-size: 18px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
  text-align: right;
  line-height: 1.2;
}

/* Activity notification — tam satır, row 3 */
.dsp-scard-act {
  grid-column: 1 / -1;
  grid-row: 3;
  margin-top: 3px;
  padding: 5px 10px;
  background: ${COLOR.bgRaised};
  border: 1px solid;
  border-radius: 7px;
  font-size: 12px;
  font-weight: ${FONT.weight.semibold};
  line-height: 1.2;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
  animation: dsp-scard-act-pulse 1.8s ease-in-out infinite;
}
@keyframes dsp-scard-act-pulse {
  0%, 100% { opacity: 1; box-shadow: 0 0 0 0 currentColor; }
  50%      { opacity: 0.78; box-shadow: 0 0 10px 1px currentColor; }
}

/* Row 4 — rules 3x2 (6 rule) */
.dsp-scard-rules {
  grid-column: 1 / -1;
  grid-row: 4;
  margin-top: 6px;
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 4px;
}
.dsp-scard-rule {
  background: ${COLOR.bg};
  border: 1px solid ${COLOR.divider};
  border-radius: 6px;
  padding: 5px 10px;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
  font-family: ${FONT.sans};
}
.dsp-scard-rule-lbl {
  font-size: 11px;
  text-transform: uppercase;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.textMuted};
  letter-spacing: 0.06em;
  line-height: 1.1;
  flex-shrink: 0;
}
.dsp-scard-rule-expr {
  display: flex;
  align-items: baseline;
  justify-content: flex-end;
  gap: 5px;
  font-family: ${FONT.mono};
  line-height: 1.1;
  min-width: 0;
}
.dsp-scard-rule-min, .dsp-scard-rule-max {
  font-size: 14px;
  color: ${COLOR.textMuted};
  font-weight: ${FONT.weight.bold};
}
.dsp-scard-rule-cmp {
  font-size: 17px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.textMuted};
}
.dsp-scard-rule-val {
  font-size: 18px;
  font-weight: ${FONT.weight.bold};
}
.dsp-scard-rule.pass { background: ${COLOR.greenSoft}; border-color: ${COLOR.greenSoft}; }
.dsp-scard-rule.pass .dsp-scard-rule-val, .dsp-scard-rule.pass .dsp-scard-rule-lbl { color: ${COLOR.green}; }
.dsp-scard-rule.fail { background: ${COLOR.redSoft}; border-color: ${COLOR.redSoft}; }
.dsp-scard-rule.fail .dsp-scard-rule-val, .dsp-scard-rule.fail .dsp-scard-rule-lbl { color: ${COLOR.red}; }
/* BEKLIYOR — henüz değerlendirilmedi, eşik görünür, value -- */
.dsp-scard-rule.waiting { background: transparent; border-color: ${COLOR.divider}; }
.dsp-scard-rule.waiting .dsp-scard-rule-val { color: ${COLOR.textMuted}; }
.dsp-scard-rule.waiting .dsp-scard-rule-lbl { color: ${COLOR.textMuted}; }
/* KAPALI — kullanıcı kapattı */
.dsp-scard-rule.disabled { background: rgba(126,126,146,0.08); border-color: ${COLOR.divider}; }
.dsp-scard-rule.disabled .dsp-scard-rule-val { color: ${COLOR.textDim}; }
.dsp-scard-rule.disabled .dsp-scard-rule-lbl { color: ${COLOR.textDim}; }
`
);

const PICK_RULES: { label: string; display: string }[] = [
  { label: 'Zaman',  display: 'Zaman' },
  { label: 'Fiyat',  display: 'Fiyat' },
  { label: 'Delta',  display: 'Delta' },
  { label: 'Spread', display: 'Spread' },
  { label: 'EvMax',  display: 'Event Max' },
  { label: 'BotMax', display: 'Bot Max' },
];

/** threshold_text parse → { min, max, cmp }
 *  "30-270s"  → { min: '30s', max: '270s' }
 *  "≥ 80"     → { cmp: '≥', max: '80' }
 *  "≤ 3%"     → { cmp: '≤', max: '3%' }
 *  "1", "3"   → { max: '1' } */
function parseThreshold(raw: string | null | undefined): { min?: string; max?: string; cmp?: string } {
  if (!raw) return {};
  const s = raw.trim();
  // range
  const r = s.match(/^(\S+?)[-–](\S+)$/);
  if (r) return { min: r[1], max: r[2] };
  // ≥ / ≤ / >= / <= / > / <
  const c = s.match(/^\s*([≥≤><]=?)\s*(.+)$/);
  if (c) return { cmp: c[1].replace('>=', '≥').replace('<=', '≤'), max: c[2] };
  return { max: s };
}

function pickRule(rules: RuleSpecContract[], label: string): RuleSpecContract | undefined {
  return rules.find((r) => r.label.toLowerCase() === label.toLowerCase().replace(' ', ''));
}

function SearchCard({ tile, onAlert }: { tile: SearchTileContract; onAlert?: AlertFn }) {
  const coin = COIN_FALLBACK[tile.coin];
  const passN = tile.rules.filter((r) => r.state === 'pass').length;
  const pnlFg = passN >= 6 ? COLOR.green : passN === 5 ? COLOR.yellow : COLOR.red;
  const coinTone = coin?.tone;
  const bgStyle = coinTone
    ? { background: `linear-gradient(135deg, ${coinTone}1f 0%, ${COLOR.surface} 55%)` }
    : undefined;
  const klass = tile.signal_ready
    ? 'ready'
    : tile.type === 'wait'
      ? 'wait'
      : tile.pnl_tone === 'loss'
        ? 'block'
        : '';

  return (
    <div className={`dsp-scard ${klass}`} style={bgStyle}>
      <div className="dsp-scard-id">
        <a
          className="dsp-scard-link"
          href={tile.event_url ?? '#'}
          target="_blank"
          rel="noopener noreferrer"
          title={`${tile.coin} Polymarket event'i aç`}
        >
          <div className="dsp-scard-logo">
            {coin?.logo_url ? <img src={coin.logo_url} alt={tile.coin} /> : null}
          </div>
        </a>
        <div className="dsp-scard-id-row">
          <a
            className="dsp-scard-ticker"
            href={tile.event_url ?? '#'}
            target="_blank"
            rel="noopener noreferrer"
            title={`${tile.coin} Polymarket event'i aç`}
          >
            <span>{tile.coin}</span>
            <span className="dsp-scard-ticker-ico" aria-hidden>🔗</span>
          </a>
          <button
            type="button"
            className="dsp-scard-icbtn dollar"
            title="Coini pasif et (aramadan çıkar)"
            aria-label="Pasif et"
            onClick={() => {
              // eslint-disable-next-line no-console
              console.log(`[preview] ${tile.coin} → pasif (Phase 2 backend)`);
            }}
          >$</button>
          <button
            type="button"
            className="dsp-scard-icbtn"
            title="Coin ayarları"
            aria-label="Ayarlar"
            onClick={() => onAlert?.('⚙', `${tile.coin} Ayarları`, `${tile.coin} coin ayarları — modal Phase 2'de eklenecek`)}
          >⚙</button>
        </div>
      </div>

      <div className="dsp-scard-pnl">
        <span className="dsp-scard-pct" style={{ color: pnlFg }}>
          {tile.pnl_big ?? '—'}
        </span>
      </div>

      <div className="dsp-scard-cells">
        <div className="dsp-scard-cell">
          <span className="dsp-scard-cell-lbl">PTB</span>
          <span className="dsp-scard-cell-val" style={{ color: COLOR.yellow }}>{tile.ptb}</span>
        </div>
        <div className="dsp-scard-cell">
          <span className="dsp-scard-cell-lbl">Canlı</span>
          <span className="dsp-scard-cell-val">{tile.live}</span>
        </div>
        <div className="dsp-scard-cell">
          <span className="dsp-scard-cell-lbl">Δ</span>
          <span className="dsp-scard-cell-val">{tile.delta}</span>
        </div>
      </div>

      {tile.activity?.text && (
        <div
          className="dsp-scard-act"
          style={(() => {
            const t = ACTIVITY_TONE[tile.activity.severity ?? 'info'];
            return { color: t.fg, borderColor: `${t.fg}44`, background: `${t.fg}14` };
          })()}
        >
          {tile.activity.text}
        </div>
      )}

      <div className="dsp-scard-rules">
        {PICK_RULES.map(({ label, display }) => {
          const rule = pickRule(tile.rules, label);
          if (!rule) {
            return (
              <div key={label} className="dsp-scard-rule disabled">
                <span className="dsp-scard-rule-lbl">{display}</span>
                <div className="dsp-scard-rule-expr"><span className="dsp-scard-rule-val">—</span></div>
              </div>
            );
          }
          const noThreshold = label === 'EvMax' || label === 'BotMax';
          const { min, max, cmp } = noThreshold ? { min: undefined, max: undefined, cmp: undefined } : parseThreshold(rule.threshold_text);
          const stateKlass = rule.state;
          // BEKLIYOR → value `--`, KAPALI → value `KAPALI`
          const displayVal =
            rule.state === 'waiting'  ? '--' :
            rule.state === 'disabled' ? 'KAPALI' :
            rule.live_value;
          return (
            <div key={label} className={`dsp-scard-rule ${stateKlass}`}>
              <span className="dsp-scard-rule-lbl">{display}</span>
              <div className="dsp-scard-rule-expr">
                {rule.state === 'disabled' ? (
                  <span className="dsp-scard-rule-val">{displayVal}</span>
                ) : (
                  <>
                    {min && <span className="dsp-scard-rule-min">{min}</span>}
                    {min && <span className="dsp-scard-rule-cmp">{'<'}</span>}
                    <span className="dsp-scard-rule-val">{displayVal}</span>
                    {rule.state !== 'waiting' && min && <span className="dsp-scard-rule-cmp">{'<'}</span>}
                    {rule.state !== 'waiting' && min && max && <span className="dsp-scard-rule-max">{max}</span>}
                    {!min && cmp && <span className="dsp-scard-rule-cmp">{cmp}</span>}
                    {!min && cmp && max && <span className="dsp-scard-rule-max">{max}</span>}
                    {!min && !cmp && max && <span className="dsp-scard-rule-max">{max}</span>}
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Sort: önce kural pass sayısı desc, eşitlikte dizideki sonraki (yeni) üste. */
function passCount(t: SearchTileContract): number {
  return t.rules.filter((r) => r.state === 'pass').length;
}
type AlertFn = (icon: string, title: string, body: string) => void;

export default function SearchRail({ tiles, onAlert }: { tiles: SearchTileContract[]; onAlert?: AlertFn }) {
  const sorted = useMemo(
    () =>
      tiles
        .map((t, i) => ({ t, i }))
        .sort((a, b) => {
          const diff = passCount(b.t) - passCount(a.t);
          if (diff !== 0) return diff;
          return b.i - a.i; // tie: sonra gelen (dizide daha sonra) üstte
        })
        .map((x) => x.t),
    [tiles]
  );
  return (
    <div className="dsp-srail-list">
      {sorted.map((t) => (
        <SearchCard key={t.tile_id} tile={t} onAlert={onAlert} />
      ))}
    </div>
  );
}
