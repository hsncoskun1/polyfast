/**
 * IdleRail — "İşlem Aranmayanlar" sekmesi.
 * SearchCard benzeri tasarım, sarı tone.
 *
 *   [logo | ticker+$+⚙]      [idle kind hero]
 *   [activity bildirim tam satır]
 *   [kural grid 3x2 (varsa) veya sebep metni]
 */

import type React from 'react';
import { COLOR, FONT, SIZE, ACTIVITY_TONE, ensureStyles } from './styles';
import { COIN_FALLBACK } from './coinRegistry';
import type { IdleTileContract } from '../api/dashboard';

ensureStyles(
  'idlerail-v5',
  `
.dsp-irail-list {
  display: grid;
  grid-auto-rows: calc((100% - 18px) / 4);
  gap: 6px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-color: ${COLOR.yellow} transparent;
  scrollbar-width: thin;
}
.dsp-irail-list::-webkit-scrollbar { width: 8px; }
.dsp-irail-list::-webkit-scrollbar-track { background: transparent; }
.dsp-irail-list::-webkit-scrollbar-thumb { background: ${COLOR.yellow}; border-radius: 4px; }

.dsp-icard {
  min-height: 0;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  border-radius: ${SIZE.radius}px;
  transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
  padding: 7px 9px;
  display: grid;
  grid-template-columns: 1fr auto;
  grid-template-rows: auto auto 1fr;
  column-gap: 8px;
  row-gap: 3px;
  min-width: 0;
  overflow: hidden;
}
.dsp-icard.tone-idle:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(234, 179, 8, 0.18);
  border-color: ${COLOR.yellow};
}
.dsp-icard.tone-settings:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(239, 68, 68, 0.18);
  border-color: ${COLOR.red};
}

/* Row 1 — id (logo + ticker + butonlar) */
.dsp-icard-id {
  grid-column: 1;
  grid-row: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.dsp-icard-logo {
  width: 32px; height: 32px;
  border-radius: 50%;
  background: ${COLOR.bg};
  display: flex; align-items: center; justify-content: center;
  overflow: hidden;
  flex-shrink: 0;
}
.dsp-icard-logo img { width: 124%; height: 124%; object-fit: contain; }
.dsp-icard-ticker {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 18px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
  letter-spacing: 0.02em;
  text-decoration: none;
  cursor: pointer;
}
.dsp-icard-ticker:hover { color: ${COLOR.yellow}; }
.dsp-icard-ticker-ico { font-size: 12px; opacity: 0.75; line-height: 1; }
.dsp-icard-icbtn {
  width: 24px; height: 24px;
  border-radius: 6px;
  border: none;
  background: ${COLOR.yellowSoft};
  color: ${COLOR.yellow};
  display: inline-flex; align-items: center; justify-content: center;
  cursor: pointer;
  font-size: 13px;
  font-weight: ${FONT.weight.bold};
  flex-shrink: 0;
  line-height: 1;
  padding: 0;
  font-family: ${FONT.sans};
}
.dsp-icard-icbtn.dollar { background: ${COLOR.greenSoft}; color: ${COLOR.green}; }
.dsp-icard-icbtn:hover { filter: brightness(1.25); }

/* Inline button pill — activity text içinde token yerine */
.dsp-icard-inline-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  margin: 0 2px;
  border-radius: 5px;
  font-family: ${FONT.sans};
  font-size: 11px;
  font-weight: ${FONT.weight.bold};
  line-height: 1;
  vertical-align: -4px;
}
.dsp-icard-inline-btn.dollar {
  background: ${COLOR.greenSoft};
  color: ${COLOR.green};
  border: 1px solid ${COLOR.green};
}
.dsp-icard-inline-btn.gear {
  background: ${COLOR.yellowSoft};
  color: ${COLOR.yellow};
  border: 1px solid ${COLOR.yellow};
}
.dsp-icard-icbtn:focus-visible { outline: 2px solid ${COLOR.cyan}; outline-offset: 2px; }
.dsp-icard-ticker:focus-visible { outline: 2px solid ${COLOR.cyan}; outline-offset: 2px; border-radius: 3px; }

/* Row 1 col 2 — kind hero */
.dsp-icard-kind {
  grid-column: 2;
  grid-row: 1;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  font-family: ${FONT.mono};
  font-size: 15px;
  font-weight: ${FONT.weight.bold};
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: ${COLOR.yellow};
}
.dsp-icard.kind-error .dsp-icard-kind { color: ${COLOR.red}; }
.dsp-icard.kind-error .dsp-icard-inline-btn.gear {
  background: ${COLOR.redSoft};
  color: ${COLOR.red};
  border-color: ${COLOR.red};
}

/* Row 2 — activity tam genişlik (scard ile aynı stil) */
.dsp-icard-act {
  grid-column: 1 / -1;
  grid-row: 2;
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
  animation: dsp-icard-act-pulse 1.8s ease-in-out infinite;
}
@keyframes dsp-icard-act-pulse {
  0%, 100% { opacity: 1; box-shadow: 0 0 0 0 currentColor; }
  50%      { opacity: 0.78; box-shadow: 0 0 10px 1px currentColor; }
}

/* Row 3 — açıklama / sebep (msg) */
.dsp-icard-msg {
  grid-column: 1 / -1;
  grid-row: 3;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 6px 12px;
  background: ${COLOR.bg};
  border: 1px solid ${COLOR.divider};
  border-radius: 7px;
  font-size: 13px;
  font-weight: ${FONT.weight.semibold};
  color: ${COLOR.textMuted};
  text-align: center;
  line-height: 1.3;
  margin-top: 3px;
}
`
);

const KIND_LABEL: Record<string, string> = {
  no_events: 'EVENT YOK',
  waiting_rules: 'İŞLEM AÇMAK İÇİN AYARLARI YAPIN',
  bot_stopped: 'BOT DURDURULDU',
  cooldown: 'COOLDOWN',
  error: 'HATA',
};

/** Activity metinde {DOLLAR} / {GEAR} token'larını inline button pill ile değiştir */
function renderActivityText(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const regex = /\{(DOLLAR|GEAR)\}/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let i = 0;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(<span key={`t${i++}`}>{text.slice(last, match.index)}</span>);
    }
    if (match[1] === 'DOLLAR') {
      parts.push(<span key={`d${i++}`} className="dsp-icard-inline-btn dollar">$</span>);
    } else {
      parts.push(<span key={`g${i++}`} className="dsp-icard-inline-btn gear">⚙</span>);
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(<span key={`t${i++}`}>{text.slice(last)}</span>);
  return parts;
}

function IdleCard({ tile, tone }: { tile: IdleTileContract; tone: 'idle' | 'settings' }) {
  const coin = tile.coin ? COIN_FALLBACK[tile.coin] : undefined;
  const coinTone = coin?.tone;
  const bgStyle = coinTone
    ? { background: `linear-gradient(135deg, ${coinTone}1f 0%, ${COLOR.surface} 55%)` }
    : undefined;
  return (
    <div className={`dsp-icard tone-${tone} kind-${tile.idle_kind}`} style={bgStyle}>
      <div className="dsp-icard-id">
        <div className="dsp-icard-logo">
          {coin?.logo_url ? <img src={coin.logo_url} alt={tile.coin ?? ''} /> : null}
        </div>
        {tile.coin ? (
          <a
            className="dsp-icard-ticker"
            href={tile.event_url ?? '#'}
            target="_blank"
            rel="noopener noreferrer"
            title={`${tile.coin} aç`}
          >
            <span>{tile.coin}</span>
            <span className="dsp-icard-ticker-ico" aria-hidden>🔗</span>
          </a>
        ) : (
          <span className="dsp-icard-ticker">SİSTEM</span>
        )}
        <button type="button" className="dsp-icard-icbtn dollar" title="Aktif" aria-label="Aktif">$</button>
        <button type="button" className="dsp-icard-icbtn" title="Ayarlar" aria-label="Ayarlar">⚙</button>
      </div>

      <div className="dsp-icard-kind">{KIND_LABEL[tile.idle_kind] ?? tile.idle_kind}</div>

      {tile.activity?.text && (
        <div
          className="dsp-icard-act"
          style={(() => {
            const t = ACTIVITY_TONE[tile.activity.severity ?? 'info'];
            return { color: t.fg, borderColor: `${t.fg}44`, background: `${t.fg}14` };
          })()}
        >
          {renderActivityText(tile.activity.text)}
        </div>
      )}

      <div className="dsp-icard-msg">{tile.msg}</div>
    </div>
  );
}

export default function IdleRail({
  tiles,
  tone = 'idle',
}: {
  tiles: IdleTileContract[];
  tone?: 'idle' | 'settings';
}) {
  return (
    <div className="dsp-irail-list">
      {tiles.map((t) => (
        <IdleCard key={t.tile_id} tile={t} tone={tone} />
      ))}
    </div>
  );
}
