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
import { COLOR, FONT, SIZE, ensureStyles } from './styles';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import SectionFilterStrip, { type SectionFilter } from './SectionFilterStrip';
import EventTile from './EventTile';
import type {
  PositionSummary,
  SearchTileContract,
  IdleTileContract,
} from '../api/dashboard';

// ╔══════════════════════════════════════════════════════════════╗
// ║  CSS                                                         ║
// ╚══════════════════════════════════════════════════════════════╝

ensureStyles(
  'composition',
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
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 22px;
}
.dsp-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.dsp-section-hdr {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 4px;
}
.dsp-section-title {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: ${FONT.weight.semibold};
  color: ${COLOR.textMuted};
}
.dsp-section-line {
  flex: 1;
  height: 1px;
  background: ${COLOR.divider};
}
.dsp-section-rows {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.dsp-empty {
  padding: 18px;
  border-radius: ${SIZE.radius}px;
  background: ${COLOR.surface};
  border: 1px dashed ${COLOR.divider};
  color: ${COLOR.textMuted};
  text-align: center;
  font-size: ${FONT.size.md};
}
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
  title: string;
  count: number;
  children: React.ReactNode;
}
function Section({ title, count, children }: SectionProps) {
  return (
    <section className="dsp-section">
      <div className="dsp-section-hdr">
        <span className="dsp-section-title">
          {title} · {count}
        </span>
        <span className="dsp-section-line" />
      </div>
      <div className="dsp-section-rows">{children}</div>
    </section>
  );
}

function EmptyState({ msg }: { msg: string }) {
  return <div className="dsp-empty">{msg}</div>;
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

export default function DashboardSidebarPreview() {
  const data = useDashboardData({ pollMs: 3000 });
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

  return (
    <div className="dsp-root">
      <Sidebar health={data.health} />
      <div className="dsp-main">
        <TopBar overview={data.overview} />
        <SectionFilterStrip
          filter={filter}
          onFilterChange={setFilter}
          counts={counts}
        />

        {data.loading && (
          <div className="dsp-loading-banner">Veri yukleniyor…</div>
        )}
        {!data.loading && data.errorStreak >= 3 && (
          <div className="dsp-error-banner">
            Backend baglantisi sorunlu — {data.errorStreak} ust uste hata
          </div>
        )}

        <div className="dsp-content">
          {showOpen && (
            <Section title="AÇIK İŞLEMLER" count={positions.length}>
              {positions.length === 0 ? (
                <EmptyState msg="Şu an açık işlem yok" />
              ) : (
                sortedPositions.map((p) => (
                  <EventTile
                    key={p.position_id}
                    variant={p.variant === 'claim' ? 'claim' : 'open'}
                    position={p}
                    coins={data.coins}
                  />
                ))
              )}
            </Section>
          )}

          {showSearch && (
            <Section title="İŞLEM ARANANLAR" count={search.length}>
              {search.length === 0 ? (
                <EmptyState msg="Şu an aranan işlem yok — bot kuralların oluşmasını bekliyor" />
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
            <Section title="İŞLEM ARANMAYANLAR" count={idle.length}>
              {idle.length === 0 ? (
                <EmptyState msg="Şu an pasif coin yok" />
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
