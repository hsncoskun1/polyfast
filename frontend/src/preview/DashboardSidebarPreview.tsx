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

import { useMemo, useState } from 'react';
import { useDashboardData } from '../hooks/useDashboardData';
import { COLOR, FONT, SIZE, SECTION_TONE, ensureStyles, type SectionKey } from './styles';
import Sidebar, { type BotLocalMode } from './Sidebar';
import TopBar from './TopBar';
import EventTile from './EventTile';
import OpenRail from './OpenRail';
import SearchRail from './SearchRail';
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
  'composition-v25',
  `
.dsp-root {
  display: flex;
  flex-direction: row;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background: ${COLOR.bg};
  font-family: ${FONT.sans};
  color: ${COLOR.text};
  line-height: 1.3;
}
.dsp-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}
.dsp-body {
  flex: 1;
  display: flex;
  min-height: 0;
}
.dsp-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}
.dsp-orail-wrap {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  margin: 6px 0 6px 10px;
  border: 2px solid ${COLOR.green};
  border-radius: 12px;
  background: linear-gradient(180deg,
    rgba(34, 197, 94, 0.22) 0px,
    rgba(34, 197, 94, 0.08) 120px,
    rgba(34, 197, 94, 0.03) 100%
  );
  box-shadow: 0 0 0 1px rgba(34,197,94,0.25) inset;
}
.dsp-orail-wrap > .dsp-orail {
  width: 100%;
  flex: 1;
  min-height: 0;
  border-left: none;
  background: transparent;
}
/* Main (İşlem Aranan) — cyan çerçeveli kutu */
.dsp-main {
  margin: 6px 10px 6px 6px;
  border: 2px solid ${COLOR.cyan};
  border-radius: 12px;
  background: linear-gradient(180deg,
    rgba(6, 182, 212, 0.22) 0px,
    rgba(6, 182, 212, 0.08) 120px,
    rgba(6, 182, 212, 0.03) 100%
  );
  box-shadow: 0 0 0 1px rgba(6,182,212,0.25) inset;
}
.dsp-orail-title {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 12px;
  padding: 9px 14px;
  border-radius: 10px 10px 0 0;
  background: linear-gradient(180deg, rgba(34,197,94,0.72), rgba(34,197,94,0.28));
  border-bottom: 1px solid;
  flex-shrink: 0;
  margin: 12px 10px 0;
  height: 36px;
  box-sizing: border-box;
}
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
  scrollbar-color: ${COLOR.cyan} transparent;
  scrollbar-width: thin;
}
.dsp-content::-webkit-scrollbar { width: 8px; }
.dsp-content::-webkit-scrollbar-track { background: transparent; }
.dsp-content::-webkit-scrollbar-thumb { background: ${COLOR.cyan}; border-radius: 4px; }
.dsp-content::-webkit-scrollbar-thumb:hover { background: #0891b2; }

/* Section — header + rows (defensive 8 tile fit) */
.dsp-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.dsp-section-hdr {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 12px;
  padding: 9px 14px;
  border-radius: 10px 10px 0 0;
  border-bottom: 1px solid;
  position: sticky;
  top: 0;
  z-index: 5;
  backdrop-filter: blur(6px);
  background: linear-gradient(180deg, rgba(6,182,212,0.85), rgba(6,182,212,0.55));
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
  width: 38px;
  height: 38px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  border: 1px solid;
  flex-shrink: 0;
}
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
  background: ${COLOR.brandSoft};
  border-bottom: 1px solid ${COLOR.borderStrong};
  font-size: ${FONT.size.sm};
  color: ${COLOR.text};
  text-align: center;
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

interface SectionProps {
  sectionKey: SectionKey;
  count: number;
  children: React.ReactNode;
}
function Section({ sectionKey, count, children }: SectionProps) {
  const tone = SECTION_TONE[sectionKey];
  return (
    <section className="dsp-section">
      <div
        className="dsp-section-hdr"
        style={{ borderBottomColor: `${tone.fg}22` }}
      >
        <div
          className="dsp-section-hdr-bar"
          style={{ background: tone.fg }}
        />
        <div className="dsp-section-hdr-text">
          <div className="dsp-section-hdr-title-row">
            <span
              className="dsp-section-hdr-dot"
              style={{
                background: tone.fg,
                boxShadow: `0 0 6px ${tone.fg}99`,
              }}
            />
            <span
              className="dsp-section-hdr-title"
              style={{ color: tone.fg }}
            >
              {tone.title}
            </span>
            <span
              className="dsp-orail-title-count"
              style={{ color: tone.fg }}
            >
              {count}
            </span>
          </div>
          <div className="dsp-section-hdr-subtitle">{tone.subtitle}</div>
        </div>
        <div className="dsp-section-hdr-spacer" />
      </div>
      <div className="dsp-section-rows">{children}</div>
    </section>
  );
}

interface EmptyStateProps {
  sectionKey: SectionKey;
  title: string;
  description: string;
  icon: string;
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
        {icon}
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

// Sirala: claim variant once, sonra open
function sortPositions(positions: PositionSummary[]): PositionSummary[] {
  return [...positions].sort((a, b) => {
    const av = a.variant === 'claim' ? 0 : 1;
    const bv = b.variant === 'claim' ? 0 : 1;
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
  return (
    <div className="dsp-modal-overlay" onClick={onCancel}>
      <div className="dsp-modal" onClick={(e) => e.stopPropagation()}>
        <div className="dsp-modal-header">
          <div className="dsp-modal-icon">⚠</div>
          <div className="dsp-modal-title">Botu durdurmak istediğinize emin misiniz?</div>
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
  // Madde 1.4: stop confirmation modal
  const [stopModalOpen, setStopModalOpen] = useState(false);

  // Mock cap kaldirildi — tum 19 senaryo gosterilir (kullanici talebi)
  const positions: PositionSummary[] = data.positions ?? [];
  const search: SearchTileContract[] = data.search ?? [];
  const idle: IdleTileContract[] = data.idle ?? [];

  const sortedPositions = useMemo(() => sortPositions(positions), [positions]);

  const showSearch = true;
  const showIdle = false;

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
          <span
            className="dsp-orail-title-dot"
            style={{
              background: SECTION_TONE.open.fg,
              boxShadow: `0 0 6px ${SECTION_TONE.open.fg}99`,
            }}
          />
          <span className="dsp-orail-title-text" style={{ color: SECTION_TONE.open.fg }}>
            AÇIK İŞLEMLER
          </span>
          <span className="dsp-orail-title-count" style={{ color: SECTION_TONE.open.fg }}>
            {positions.filter((p) => p.variant !== 'claim').length}
          </span>
        </div>
        <OpenRail positions={sortedPositions} />
      </div>
      <div className="dsp-main">

        {data.loading && (
          <div className="dsp-loading-banner">Veri yükleniyor…</div>
        )}
        {!data.loading && data.errorStreak >= 3 && (
          <div className="dsp-error-banner">
            Backend bağlantısı sorunlu — {data.errorStreak} üst üste hata
          </div>
        )}

        <div className="dsp-content">
          {showSearch && (
            <Section sectionKey="search" count={search.length}>
              {search.length === 0 ? (
                <EmptyState
                  sectionKey="search"
                  icon="⌕"
                  title="Sinyal aranıyor"
                  description="Kuralların tüm coinler için oluşmasını bekliyoruz — eligible olanlar burada listelenecek"
                  online={online}
                  statusText={statusText}
                />
              ) : (
                <SearchRail tiles={search.slice(0, 4)} />
              )}
            </Section>
          )}

          {showIdle && (
            <Section sectionKey="idle" count={idle.length}>
              {idle.length === 0 ? (
                <EmptyState
                  sectionKey="idle"
                  icon="⊙"
                  title="Pasif coin yok"
                  description="Tüm coinler aktif ya da henüz kayıt yok — manuel kapatılan coinler burada görünür"
                  online={online}
                  statusText={statusText}
                />
              ) : (
                idle.map((i) => (
                  <EventTile
                    key={i.tile_id}
                    variant="idle"
                    idle={i}
                    coins={data.coins}
                  />
                ))
              )}
            </Section>
          )}
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
