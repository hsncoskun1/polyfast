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
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import SectionFilterStrip, { type SectionFilter } from './SectionFilterStrip';
import EventTile from './EventTile';
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
  'composition-v3',
  `
.dsp-root {
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background: ${COLOR.bg};
  font-family: ${FONT.sans};
  color: ${COLOR.text};
}
.dsp-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}
.dsp-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px 22px 24px;
  display: flex;
  flex-direction: column;
  gap: 22px;
}

/* Section — header + rows (turn 2: tighter ritim) */
.dsp-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.dsp-section-hdr {
  display: flex;
  align-items: stretch;
  gap: 12px;
  padding: 2px 0 6px;
  border-bottom: 1px solid;
  position: relative;
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
  flex: 1;
  min-width: 0;
}
.dsp-section-hdr-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dsp-section-hdr-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dsp-section-hdr-title {
  font-size: 13px;
  font-weight: ${FONT.weight.bold};
  letter-spacing: 0.07em;
  text-transform: uppercase;
}
.dsp-section-hdr-subtitle {
  font-size: 11px;
  color: ${COLOR.textMuted};
  font-weight: ${FONT.weight.medium};
  padding-left: 17px;
}
.dsp-section-hdr-badge {
  font-family: ${FONT.mono};
  font-size: 12px;
  font-weight: ${FONT.weight.bold};
  padding: 4px 10px;
  border-radius: 12px;
  align-self: center;
  border: 1px solid;
  min-width: 32px;
  text-align: center;
  letter-spacing: 0.02em;
}
.dsp-section-rows {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* Empty state — premium kart, kompakt (turn 2: 110px) */
.dsp-empty {
  padding: 20px 20px;
  border-radius: ${SIZE.radiusLg}px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.border};
  border-left-width: 3px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  text-align: center;
  min-height: 110px;
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
          </div>
          <div className="dsp-section-hdr-subtitle">{tone.subtitle}</div>
        </div>
        <div
          className="dsp-section-hdr-badge"
          style={{
            background: tone.bg,
            color: tone.fg,
            borderColor: tone.border,
          }}
        >
          {count}
        </div>
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

  const [filter, setFilter] = useState<SectionFilter>('all');

  const positions: PositionSummary[] = data.positions ?? [];
  const search: SearchTileContract[] = data.search ?? [];
  const idle: IdleTileContract[] = data.idle ?? [];

  const sortedPositions = useMemo(() => sortPositions(positions), [positions]);

  const counts = {
    all: positions.length + search.length + idle.length,
    open: positions.length,
    search: search.length,
    idle: idle.length,
  };

  const showOpen = filter === 'all' || filter === 'open';
  const showSearch = filter === 'all' || filter === 'search';
  const showIdle = filter === 'all' || filter === 'idle';

  // Status chip: hep gosterilir (Q3 = a)
  const online = data.errorStreak < 3;
  const statusText = online
    ? 'Backend bağlı · 3s polling'
    : `Bağlantı sorunlu · ${data.errorStreak} retry`;

  return (
    <div className="dsp-root">
      <Sidebar health={data.health} />
      <div className="dsp-main">
        <TopBar overview={data.overview} mockMode={mockMode} />
        <SectionFilterStrip
          filter={filter}
          onFilterChange={setFilter}
          counts={counts}
        />

        {data.loading && (
          <div className="dsp-loading-banner">Veri yükleniyor…</div>
        )}
        {!data.loading && data.errorStreak >= 3 && (
          <div className="dsp-error-banner">
            Backend bağlantısı sorunlu — {data.errorStreak} üst üste hata
          </div>
        )}

        <div className="dsp-content">
          {showOpen && (
            <Section sectionKey="open" count={positions.length}>
              {positions.length === 0 ? (
                <EmptyState
                  sectionKey="open"
                  icon="◯"
                  title="Henüz açık işlem yok"
                  description="Bot yeni 5M event arıyor — sinyal oluştuğunda burada görünür"
                  online={online}
                  statusText={statusText}
                />
              ) : (
                sortedPositions.map((p) => (
                  <EventTile
                    key={p.position_id}
                    variant={p.variant === 'claim' ? 'claim' : 'open'}
                    position={p}
                    coins={data.coins}
                    claims={data.claims}
                  />
                ))
              )}
            </Section>
          )}

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
                search.map((s) => (
                  <EventTile
                    key={s.tile_id}
                    variant="search"
                    search={s}
                    coins={data.coins}
                  />
                ))
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
  );
}
