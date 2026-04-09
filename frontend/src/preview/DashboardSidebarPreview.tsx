/**
 * DashboardSidebarPreview — composition file.
 *
 * useDashboardData hook'undan tum 7 endpoint verisini ceker, sidebar +
 * top bar + section filter strip + main content (3 section + tile'lar)
 * komposizasyonu yapar.
 *
 * Mevcut DashboardPreview'a dokunmaz. Ayri preview, ayri dosya.
 * Erisim: localhost:5173/?preview=sidebar
 *
 * 1. tur kompakt: section + empty state burada local. Stabil kaldiginda
 * ayri Section/EmptyState bilesenlerine cikarilir.
 *
 * Animasyon: YOK
 * Mock fallback: YOK (durust empty state)
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useDashboardData } from '../hooks/useDashboardData';
import { COLOR, FONT, SIZE, SECTION_TONE, ensureStyles, type SectionKey } from './styles';
import Sidebar, { type BotLocalMode } from './Sidebar';
import TopBar from './TopBar';
import OpenRail from './OpenRail';
import SearchRail from './SearchRail';
import IdleRail from './IdleRail';
import { MOCK_DATA } from './mockData';
import type {
  PositionSummary,
  SearchTileContract,
  IdleTileContract,
} from '../api/dashboard';

// ╔══════════════════════════════════════════════════════════════╗
// ║  CSS                                                         ║
// ╚══════════════════════════════════════════════════════════════╝

ensureStyles(
  'composition-v53',
  `
.dsp-root {
  display: flex;
  flex-direction: row;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background:
    radial-gradient(circle at 0% 0%, rgba(6, 182, 212, 0.10) 0%, transparent 45%),
    radial-gradient(circle at 100% 100%, rgba(0, 0, 0, 0.6) 0%, transparent 60%),
    ${COLOR.bg};
  font-family: ${FONT.sans};
  color: ${COLOR.text};
  line-height: 1.3;
}
.dsp-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.dsp-body {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: visible;
}
.dsp-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: visible;
}
.dsp-orail-wrap {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: visible;
  margin: 42px 0 6px 10px;
  padding: 10px;
  background: linear-gradient(180deg,
    rgba(34, 197, 94, 0.22) 0px,
    rgba(34, 197, 94, 0.08) 150px,
    rgba(34, 197, 94, 0.03) 100%
  );
  border: 2px solid ${COLOR.green};
  border-radius: 0 12px 12px 12px;
  position: relative;
}
/* Chrome-tab: wrap'in sol üstüne "yapışık" tab */
.dsp-orail-wrap > .dsp-orail-title {
  position: absolute;
  top: -38px;
  left: -2px;
  height: 38px;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 0 22px;
  background: linear-gradient(180deg, rgba(34,197,94,0.82), rgba(34,197,94,0.42));
  border: 2px solid ${COLOR.green};
  border-bottom: none;
  border-radius: 12px 12px 0 0;
  box-sizing: border-box;
  margin: 0;
  white-space: nowrap;
}
.dsp-orail-wrap > .dsp-orail {
  width: 100%;
  flex: 1;
  min-height: 0;
  border: none;
  background: transparent;
  padding: 0;
}
/* Main panel — aktif sekme tonuna göre renkli çerçeve + gradient */
.dsp-main {
  margin: 42px 10px 6px 6px;
  border: 2px solid var(--dsp-main-tone, ${COLOR.cyan});
  border-radius: 0 12px 12px 12px;
  background: linear-gradient(180deg,
    color-mix(in srgb, var(--dsp-main-tone, ${COLOR.cyan}) 26%, transparent) 0px,
    color-mix(in srgb, var(--dsp-main-tone, ${COLOR.cyan}) 10%, transparent) 150px,
    color-mix(in srgb, var(--dsp-main-tone, ${COLOR.cyan}) 4%, transparent) 100%
  );
  transition: border-color 0.2s, background 0.2s;
  position: relative;
}
.dsp-main.tab-search   { --dsp-main-tone: ${COLOR.cyan}; }
.dsp-main.tab-idle     { --dsp-main-tone: ${COLOR.yellow}; }
.dsp-main.tab-settings { --dsp-main-tone: ${COLOR.red}; }
.dsp-orail-title-dot {
  width: 11px; height: 11px; border-radius: 50%;
  flex-shrink: 0;
}
.dsp-orail-title-text {
  font-size: 13px;
  font-weight: ${FONT.weight.bold};
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.dsp-orail-title-count {
  font-family: ${FONT.mono};
  font-size: 14px;
  font-weight: ${FONT.weight.bold};
  line-height: 1;
  padding: 3px 9px;
  border: 1.5px solid #ffffff;
  border-radius: 6px;
  color: #ffffff;
}
.dsp-content {
  flex: 1;
  overflow-y: auto;
  padding: 6px 10px 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  scrollbar-color: var(--dsp-main-tone, ${COLOR.cyan}) transparent;
  scrollbar-width: thin;
}
.dsp-content::-webkit-scrollbar { width: 8px; }
.dsp-content::-webkit-scrollbar-track { background: transparent; }
.dsp-content::-webkit-scrollbar-thumb {
  background: var(--dsp-main-tone, ${COLOR.cyan});
  border-radius: 4px;
}
.dsp-content::-webkit-scrollbar-thumb:hover { filter: brightness(0.85); }

/* Section — header + rows (defensive 8 tile fit) */
.dsp-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
/* Main tab bar — chrome tab stili, 3 inline sekme sola yaslı */
.dsp-main-tabs {
  position: absolute;
  top: -38px;
  left: -2px;
  right: -2px;
  display: flex;
  gap: 4px;
  padding: 0;
  height: 38px;
  z-index: 5;
  overflow: visible;
}
.dsp-main-tab {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
  height: 38px;
  padding: 0 22px;
  border: 2px solid color-mix(in srgb, var(--dsp-main-tone, ${COLOR.cyan}) 35%, transparent);
  border-bottom: none;
  border-radius: 12px 12px 0 0;
  background: color-mix(in srgb, var(--dsp-main-tone, ${COLOR.cyan}) 15%, transparent);
  color: ${COLOR.textMuted};
  font-family: ${FONT.sans};
  font-size: 13px;
  font-weight: ${FONT.weight.bold};
  letter-spacing: 0.08em;
  text-transform: uppercase;
  cursor: pointer;
  opacity: 0.75;
  transition: opacity 0.15s, background 0.15s;
  white-space: nowrap;
  box-sizing: border-box;
  flex: 1 1 auto;
  min-width: 0;
}
.dsp-main-tab-label {
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.dsp-main-tab-label { overflow: visible; }
.dsp-main-tab:hover { opacity: 0.9; }
.dsp-main-tab:focus-visible { outline: 2px solid ${COLOR.cyan}; outline-offset: 2px; }

/* Flash dot — yeni data vurgusu (count değişince 2s) */
.dsp-flash-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: ${COLOR.cyan};
  margin-left: 6px;
  vertical-align: 2px;
  opacity: 0;
  box-shadow: 0 0 8px ${COLOR.cyan};
  animation: dsp-flash 2s ease-out;
}
.dsp-flash-dot.open { background: ${COLOR.green}; box-shadow: 0 0 8px ${COLOR.green}; }
.dsp-flash-dot.idle { background: ${COLOR.yellow}; box-shadow: 0 0 8px ${COLOR.yellow}; }
.dsp-flash-dot.settings { background: ${COLOR.red}; box-shadow: 0 0 8px ${COLOR.red}; }
@keyframes dsp-flash {
  0%   { opacity: 0; transform: scale(0.6); }
  10%  { opacity: 1; transform: scale(1.3); }
  70%  { opacity: 0.8; transform: scale(1); }
  100% { opacity: 0; transform: scale(1); }
}
@media (prefers-reduced-motion: reduce) {
  .dsp-flash-dot { animation: none !important; opacity: 0; }
}
.dsp-modal-btn:focus-visible { outline: 2px solid ${COLOR.cyan}; outline-offset: 2px; }

/* Accessibility — kullanıcı OS'te 'animasyon azalt' tercihi yaptıysa tüm pulse/loop dursun */
@media (prefers-reduced-motion: reduce) {
  .dsp-scard-act,
  .dsp-icard-act,
  .dsp-ocard-exit-pop,
  .dsp-sb-bot-status.running .dsp-sb-bot-status-dot {
    animation: none !important;
  }
  .dsp-ocard,
  .dsp-scard,
  .dsp-icard {
    transition: none !important;
  }
}
.dsp-main-tab.active { opacity: 1; color: #ffffff; }
.dsp-main-tab.tone-search.active   { background: linear-gradient(180deg, rgba(6,182,212,0.82), rgba(6,182,212,0.42)); border-color: ${COLOR.cyan}; color: #fff; }
.dsp-main-tab.tone-search.active::after { color: ${COLOR.cyan}; }
.dsp-main-tab.tone-idle.active     { background: linear-gradient(180deg, rgba(234,179,8,0.82), rgba(234,179,8,0.42)); border-color: ${COLOR.yellow}; color: #fff; }
.dsp-main-tab.tone-idle.active::after { color: ${COLOR.yellow}; }
.dsp-main-tab.tone-settings.active { background: linear-gradient(180deg, rgba(239,68,68,0.82), rgba(239,68,68,0.42)); border-color: ${COLOR.red}; color: #fff; }
.dsp-main-tab.tone-settings.active::after { color: ${COLOR.red}; }
.dsp-main-tab-count {
  font-family: ${FONT.mono};
  font-size: 14px;
  padding: 3px 9px;
  border: 1.5px solid currentColor;
  border-radius: 6px;
  line-height: 1;
}
/* Legacy section hdr — backwards compat (open rail kullanılmıyor) */
.dsp-section-hdr {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 14px;
  border-radius: 10px 10px 0 0;
  border-bottom: 1px solid;
  background: linear-gradient(180deg, rgba(6,182,212,0.72), rgba(6,182,212,0.28));
  margin: 6px 10px 0;
  height: 36px;
  box-sizing: border-box;
}
.dsp-section-hdr-bar { display: none; }
.dsp-section-hdr-text { flex: 0 0 auto; }
.dsp-section-hdr-spacer { display: none; }
.dsp-section-hdr-title {
  font-size: 13px !important;
  letter-spacing: 0.1em !important;
}
.dsp-section-hdr-dot {
  width: 9px !important;
  height: 9px !important;
}
.dsp-section-hdr-bar {
  width: 3px;
  border-radius: 2px;
  flex-shrink: 0;
}
.dsp-section-hdr-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
  flex: 0 0 auto;
  min-width: 0;
}
.dsp-section-hdr-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.dsp-section-hdr-title-row .dsp-orail-title-count {
  font-size: 14px;
  padding: 3px 9px;
  border: 1.5px solid #ffffff;
  border-radius: 6px;
  color: #ffffff !important;
}
.dsp-section-hdr-spacer {
  flex: 1;
}
.dsp-section-hdr-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dsp-section-hdr-title {
  font-size: 11px;
  font-weight: ${FONT.weight.bold};
  letter-spacing: 0.07em;
  text-transform: uppercase;
}
.dsp-section-hdr-subtitle {
  display: none; /* defensive 850: gizli, header daha kisa */
  font-size: 10px;
  color: ${COLOR.textMuted};
  font-weight: ${FONT.weight.medium};
  padding-left: 17px;
}
.dsp-section-hdr-badge {
  font-family: ${FONT.mono};
  font-size: 11px;
  font-weight: ${FONT.weight.bold};
  padding: 1px 8px;
  border-radius: 9px;
  border: 1px solid;
  min-width: 24px;
  text-align: center;
  letter-spacing: 0.02em;
  line-height: 1.4;
}
/* Section rows — single column (tek tile per row, full width) */
.dsp-section-rows {
  display: grid;
  grid-template-columns: 1fr;
  gap: 4px;
}

/* Empty state — premium kart, kompakt (turn 4: tile yuksekligine yakin) */
.dsp-empty {
  padding: 14px 18px;
  border-radius: ${SIZE.radiusLg}px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.border};
  border-left-width: 3px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  text-align: center;
  min-height: 96px;
  justify-content: center;
}
.dsp-empty-icon {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1.5px solid;
  flex-shrink: 0;
}
.dsp-empty-icon svg { width: 28px; height: 28px; }
.dsp-empty-title {
  font-size: 13px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
  letter-spacing: 0.02em;
}
.dsp-empty-desc {
  font-size: 11.5px;
  color: ${COLOR.textMuted};
  line-height: 1.5;
  max-width: 380px;
}
.dsp-empty-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 10px;
  background: ${COLOR.bgRaised};
  border: 1px solid ${COLOR.divider};
  font-size: 9.5px;
  color: ${COLOR.textMuted};
  font-family: ${FONT.mono};
  margin-top: 2px;
}
.dsp-empty-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: ${COLOR.green};
}
.dsp-empty-status-dot.err { background: ${COLOR.red}; }

.dsp-loading-banner {
  padding: 8px 18px;
  background: ${COLOR.cyanSoft};
  border-bottom: 1px solid ${COLOR.cyan};
  font-size: ${FONT.size.sm};
  color: ${COLOR.cyan};
  text-align: center;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  font-weight: ${FONT.weight.semibold};
}
.dsp-loading-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid ${COLOR.cyan};
  border-top-color: transparent;
  border-radius: 50%;
  animation: dsp-loading-spin 0.9s linear infinite;
  flex-shrink: 0;
}
@keyframes dsp-loading-spin {
  to { transform: rotate(360deg); }
}
@media (prefers-reduced-motion: reduce) {
  .dsp-loading-spinner { animation: none !important; }
}
.dsp-error-banner {
  padding: 8px 18px;
  background: ${COLOR.redSoft};
  border-bottom: 1px solid ${COLOR.red};
  font-size: ${FONT.size.sm};
  color: ${COLOR.red};
  text-align: center;
}

/* Stop confirmation modal — madde 1.4 */
.dsp-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(5, 3, 12, 0.78);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}
.dsp-modal {
  background: ${COLOR.bgRaised};
  border: 1px solid ${COLOR.borderStrong};
  border-radius: ${SIZE.radiusLg}px;
  max-width: 460px;
  width: 100%;
  padding: 26px 26px 22px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6), 0 0 0 1px ${COLOR.brandSoft};
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.dsp-modal-header {
  display: flex;
  align-items: center;
  gap: 12px;
}
.dsp-modal-icon {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: ${COLOR.redSoft};
  border: 1px solid ${COLOR.red};
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  color: ${COLOR.red};
  flex-shrink: 0;
}
.dsp-modal-title {
  font-size: 16px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
  letter-spacing: 0.02em;
}
.dsp-modal-body {
  font-size: 13px;
  color: ${COLOR.text};
  line-height: 1.55;
  opacity: 0.85;
}
.dsp-modal-body strong {
  color: ${COLOR.red};
  font-weight: ${FONT.weight.bold};
}
.dsp-modal-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  margin-top: 4px;
}
.dsp-modal-btn {
  padding: 9px 18px;
  border-radius: ${SIZE.radius}px;
  font-size: 13px;
  font-weight: ${FONT.weight.semibold};
  font-family: ${FONT.sans};
  cursor: pointer;
  border: 1px solid;
}
.dsp-modal-btn.cancel {
  background: ${COLOR.surface};
  border-color: ${COLOR.border};
  color: ${COLOR.text};
}
.dsp-modal-btn.cancel:hover { background: ${COLOR.surfaceHover}; }
.dsp-modal-btn.danger {
  background: ${COLOR.red};
  border-color: ${COLOR.red};
  color: #fff;
}
.dsp-modal-btn.danger:hover { filter: brightness(1.1); }
`
);

// ╔══════════════════════════════════════════════════════════════╗
// ║  Local helpers                                               ║
// ╚══════════════════════════════════════════════════════════════╝


/** Empty state için küçük inline SVG illüstrasyonlar */
/**
 * useCountFlash — count değişince 2 saniye boyunca true döner,
 * sonra false'a düşer. UI'da "yeni data" flash vurgusu için.
 */
function useCountFlash(count: number, duration = 2000): boolean {
  const prev = useRef<number>(count);
  const [flash, setFlash] = useState(false);
  useEffect(() => {
    if (count !== prev.current) {
      prev.current = count;
      setFlash(true);
      const id = setTimeout(() => setFlash(false), duration);
      return () => clearTimeout(id);
    }
    return undefined;
  }, [count, duration]);
  return flash;
}

function EmptyIcon({ kind }: { kind: 'search' | 'idle' | 'settings' }) {
  if (kind === 'search') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="10.5" cy="10.5" r="6.5" />
        <line x1="21" y1="21" x2="15.2" y2="15.2" />
      </svg>
    );
  }
  if (kind === 'idle') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="9" />
        <line x1="8" y1="12" x2="16" y2="12" />
      </svg>
    );
  }
  // settings
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="2.5" />
      <path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 01-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 010-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3h.1a1.7 1.7 0 001-1.5V3a2 2 0 014 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8v.1a1.7 1.7 0 001.5 1H21a2 2 0 010 4h-.1a1.7 1.7 0 00-1.5 1z" />
    </svg>
  );
}

interface EmptyStateProps {
  sectionKey: SectionKey;
  title: string;
  description: string;
  icon: 'search' | 'idle' | 'settings';
  /** Backend canli mi (status chip rengi icin) */
  online: boolean;
  /** Status chip metni */
  statusText: string;
}
function EmptyState({
  sectionKey,
  title,
  description,
  icon,
  online,
  statusText,
}: EmptyStateProps) {
  const tone = SECTION_TONE[sectionKey];
  return (
    <div
      className="dsp-empty"
      style={{ borderLeftColor: tone.fg }}
    >
      <div
        className="dsp-empty-icon"
        style={{
          color: tone.fg,
          borderColor: `${tone.fg}55`,
          background: tone.bg,
        }}
      >
        <EmptyIcon kind={icon} />
      </div>
      <div className="dsp-empty-title">{title}</div>
      <div className="dsp-empty-desc">{description}</div>
      <div className="dsp-empty-status">
        <span
          className={`dsp-empty-status-dot${online ? '' : ' err'}`}
        />
        <span>{statusText}</span>
      </div>
    </div>
  );
}

// Sirala: open variant üstte, claim altta
function sortPositions(positions: PositionSummary[]): PositionSummary[] {
  return [...positions].sort((a, b) => {
    const av = a.variant === 'claim' ? 1 : 0;
    const bv = b.variant === 'claim' ? 1 : 0;
    return av - bv;
  });
}

// (Mock cap kaldirildi — tum 19 senaryo gozukuyor, kullanici talebi)

interface StopConfirmModalProps {
  openPositionCount: number;
  onCancel: () => void;
  onConfirm: () => void;
}
function StopConfirmModal({
  openPositionCount,
  onCancel,
  onConfirm,
}: StopConfirmModalProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onCancel]);

  return (
    <div className="dsp-modal-overlay" role="presentation">
      <div
        className="dsp-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="dsp-stop-title"
      >
        <div className="dsp-modal-header">
          <div className="dsp-modal-icon">⚠</div>
          <div className="dsp-modal-title" id="dsp-stop-title">Botu durdurmak istediğinize emin misiniz?</div>
        </div>
        <div className="dsp-modal-body">
          Şu an <strong>{openPositionCount} açık pozisyon</strong> var.
          Botu durdurursanız bu pozisyonları manuel kapatmanız gerekecek —
          TP/SL/FS otomatik tetiklenmez.
        </div>
        <div className="dsp-modal-actions">
          <button type="button" className="dsp-modal-btn cancel" onClick={onCancel}>
            Vazgeç
          </button>
          <button type="button" className="dsp-modal-btn danger" onClick={onConfirm}>
            Yine de durdur
          </button>
        </div>
      </div>
    </div>
  );
}

// ╔══════════════════════════════════════════════════════════════╗
// ║  Public composition                                          ║
// ╚══════════════════════════════════════════════════════════════╝

export interface DashboardSidebarPreviewProps {
  /** Mock showcase modu — true iken hook yerine MOCK_DATA kullanilir,
   *  hicbir backend istegi gitmez, top bar 'MOCK' badge gosterir. */
  mockMode?: boolean;
}

export default function DashboardSidebarPreview({
  mockMode = false,
}: DashboardSidebarPreviewProps = {}) {
  // Mock mod: hook'u CALISTIRMA, statik veri kullan
  // Gercek mod: hook canli backend'e baglanir
  // Hook her zaman cagrilmali (rules of hooks) — ama mock mod'da
  // enabled=false geciyoruz, polling olmaz
  const liveData = useDashboardData({
    pollMs: 3000,
    enabled: !mockMode,
    fetchOnMount: !mockMode,
  });
  const data = mockMode ? MOCK_DATA : liveData;

  // Madde 1.3: bot lifecycle lokal state (frontend-only, backend wiring sonra)
  const [botLocalMode, setBotLocalMode] = useState<BotLocalMode>('running');
  const [mainTab, setMainTab] = useState<'search' | 'idle' | 'settings'>('search');
  // Madde 1.4: stop confirmation modal
  const [stopModalOpen, setStopModalOpen] = useState(false);

  // Mock cap kaldirildi — tum 19 senaryo gosterilir (kullanici talebi)
  const positions: PositionSummary[] = data.positions ?? [];
  const search: SearchTileContract[] = data.search ?? [];
  const idle: IdleTileContract[] = data.idle ?? [];

  const sortedPositions = useMemo(() => sortPositions(positions), [positions]);

  // 'İşlem Aranmayan' = pasif coin (manuel kapatılmış, bot_stopped)
  // 'Ayar Gerekli'     = müdahale gerektiren (waiting_rules: ayar yok, error: hata)
  const idleOnly = idle.filter((i) => i.idle_kind === 'bot_stopped');
  const idleSettings = idle.filter((i) => i.idle_kind === 'waiting_rules' || i.idle_kind === 'error');
  const mainCounts = { search: search.length, idle: idleOnly.length, settings: idleSettings.length };
  const openCount = positions.filter((p) => p.variant !== 'claim').length;
  const flashOpen     = useCountFlash(openCount);
  const flashSearch   = useCountFlash(mainCounts.search);
  const flashIdle     = useCountFlash(mainCounts.idle);
  const flashSettings = useCountFlash(mainCounts.settings);

  // Status chip: hep gosterilir (Q3 = a)
  const online = data.errorStreak < 3;
  const statusText = online
    ? 'Backend bağlı · 3s polling'
    : `Bağlantı sorunlu · ${data.errorStreak} retry`;

  // Bot action handler — Pause/Stop/Start semantik (madde 1.3)
  // Stop iken acik pozisyon varsa modal ac (madde 1.4)
  const handleBotAction = (action: 'start' | 'pause' | 'stop') => {
    if (action === 'start') {
      setBotLocalMode('running');
      return;
    }
    if (action === 'pause') {
      setBotLocalMode('paused');
      return;
    }
    if (action === 'stop') {
      if (positions.length > 0 && botLocalMode !== 'stopped') {
        setStopModalOpen(true);
        return;
      }
      setBotLocalMode('stopped');
    }
  };
  const confirmStop = () => {
    setBotLocalMode('stopped');
    setStopModalOpen(false);
  };
  const cancelStop = () => setStopModalOpen(false);

  return (
    <div className="dsp-root">
      <Sidebar
        health={data.health}
        localBotMode={botLocalMode}
        onBotAction={handleBotAction}
      />
      <div className="dsp-right">
        <TopBar overview={data.overview} />
        <div className="dsp-body">
      <div className="dsp-orail-wrap">
        <div
          className="dsp-orail-title"
          style={{ borderBottomColor: `${SECTION_TONE.open.fg}22` }}
        >
          <span className="dsp-orail-title-text" style={{ color: SECTION_TONE.open.fg }}>
            AÇIK İŞLEMLER
          </span>
          <span className="dsp-orail-title-count" style={{ color: SECTION_TONE.open.fg }}>
            {openCount}
          </span>
          {flashOpen && <span className="dsp-flash-dot open" aria-hidden />}
        </div>
        <OpenRail positions={sortedPositions} claims={data.claims ?? undefined} />
      </div>
      <div className={`dsp-main tab-${mainTab}`}>

        {data.loading && (
          <div className="dsp-loading-banner">
            <span className="dsp-loading-spinner" aria-hidden />
            <span>Veri yükleniyor…</span>
          </div>
        )}
        {!data.loading && data.errorStreak >= 3 && (
          <div className="dsp-error-banner">
            Backend bağlantısı sorunlu — {data.errorStreak} üst üste hata
          </div>
        )}

        <div className="dsp-main-tabs">
          {([
            { key: 'search',   label: 'İşlem Arananlar',    count: mainCounts.search,   flash: flashSearch },
            { key: 'idle',     label: 'İşlem Aranmayanlar', count: mainCounts.idle,     flash: flashIdle },
            { key: 'settings', label: 'Ayar Gerekli',       count: mainCounts.settings, flash: flashSettings },
          ] as const).map((t) => (
            <button
              key={t.key}
              type="button"
              className={`dsp-main-tab ${mainTab === t.key ? 'active' : ''} tone-${t.key}`}
              onClick={() => setMainTab(t.key)}
            >
              <span className="dsp-main-tab-label">{t.label}</span>
              <span className="dsp-main-tab-count">{t.count}</span>
              {t.flash && <span className={`dsp-flash-dot ${t.key}`} aria-hidden />}
            </button>
          ))}
        </div>
        <div className="dsp-content">
          {mainTab === 'search' && (search.length === 0 ? (
            <EmptyState
              sectionKey="search"
              icon="search"
              title="Sinyal aranıyor"
              description="Kuralların tüm coinler için oluşmasını bekliyoruz — eligible olanlar burada listelenecek"
              online={online}
              statusText={statusText}
            />
          ) : (
            <SearchRail tiles={search} />
          ))}
          {mainTab === 'idle' && (idleOnly.length === 0 ? (
            <EmptyState
              sectionKey="idle"
              icon="idle"
              title="Pasif coin yok"
              description="Tüm coinler aktif ya da henüz kayıt yok — manuel kapatılan coinler burada görünür"
              online={online}
              statusText={statusText}
            />
          ) : (
            <IdleRail tiles={idleOnly} tone="idle" />
          ))}
          {mainTab === 'settings' && (idleSettings.length === 0 ? (
            <EmptyState
              sectionKey="idle"
              icon="settings"
              title="Ayar gerektiren coin yok"
              description="Bot çalışır durumda — hata/duraklamış coin olduğunda burada görünür"
              online={online}
              statusText={statusText}
            />
          ) : (
            <IdleRail tiles={idleSettings} tone="settings" />
          ))}
        </div>
      </div>
        </div>
      </div>
      {stopModalOpen && (
        <StopConfirmModal
          openPositionCount={positions.length}
          onCancel={cancelStop}
          onConfirm={confirmStop}
        />
      )}
    </div>
  );
}
