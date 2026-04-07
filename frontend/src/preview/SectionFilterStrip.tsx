/**
 * SectionFilterStrip — top bar altinda secondary strip (~40px).
 *
 * Section filter + ozet alani. 5 tab badge:
 *  - Tum Marketler (toplam sayac)
 *  - Acik Islemler (open + claim)
 *  - Aranan (search)
 *  - Aranmayan (idle)
 *
 * Karar (plan v2 4. madde):
 *  - secim/ozet alani burada olur
 *  - main content section header'lari sakin kalir, sayac/badge tekrari olmaz
 *  - exclusive selection: tek tab aktif
 *  - 'Tum Marketler' = expand all
 *
 * 1. tur kompakt: animasyon yok, statik tab.
 */

import { COLOR, FONT, SIZE, ensureStyles } from './styles';

// ╔══════════════════════════════════════════════════════════════╗
// ║  CSS                                                         ║
// ╚══════════════════════════════════════════════════════════════╝

ensureStyles(
  'sectionstrip',
  `
.dsp-sfs {
  height: ${SIZE.sectionStripHeight}px;
  flex-shrink: 0;
  background: ${COLOR.bg};
  border-bottom: 1px solid ${COLOR.divider};
  display: flex;
  align-items: center;
  padding: 0 18px;
  gap: 6px;
  font-family: ${FONT.sans};
}
.dsp-sfs-tab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: ${SIZE.radius}px;
  background: transparent;
  border: 1px solid transparent;
  font-size: ${FONT.size.md};
  font-weight: ${FONT.weight.medium};
  color: ${COLOR.textMuted};
  cursor: pointer;
  font-family: ${FONT.sans};
  white-space: nowrap;
}
.dsp-sfs-tab:hover { color: ${COLOR.text}; }
.dsp-sfs-tab.active {
  background: ${COLOR.brandSoft};
  border-color: ${COLOR.borderStrong};
  color: ${COLOR.text};
}
.dsp-sfs-tab .dsp-sfs-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.dsp-sfs-tab .dsp-sfs-count {
  font-family: ${FONT.mono};
  font-size: 10px;
  font-weight: ${FONT.weight.bold};
  padding: 1px 6px;
  border-radius: 8px;
  background: ${COLOR.surface};
  color: ${COLOR.textMuted};
  min-width: 18px;
  text-align: center;
}
.dsp-sfs-tab.active .dsp-sfs-count {
  background: ${COLOR.brand};
  color: ${COLOR.bg};
}
`
);

// ╔══════════════════════════════════════════════════════════════╗
// ║  Public component                                            ║
// ╚══════════════════════════════════════════════════════════════╝

export type SectionFilter = 'all' | 'open' | 'search' | 'idle';

export interface SectionFilterStripProps {
  filter: SectionFilter;
  onFilterChange: (next: SectionFilter) => void;
  counts: {
    all: number;
    open: number;
    search: number;
    idle: number;
  };
}

interface TabDef {
  key: SectionFilter;
  label: string;
  dot?: string;
}

const TABS: TabDef[] = [
  { key: 'all', label: 'Tüm Marketler' },
  { key: 'open', label: 'Açık İşlemler', dot: COLOR.green },
  { key: 'search', label: 'Aranan', dot: COLOR.brand },
  { key: 'idle', label: 'Aranmayan', dot: COLOR.cyan },
];

export default function SectionFilterStrip({
  filter,
  onFilterChange,
  counts,
}: SectionFilterStripProps) {
  return (
    <div className="dsp-sfs">
      {TABS.map((tab) => {
        const active = filter === tab.key;
        const count = counts[tab.key];
        return (
          <button
            key={tab.key}
            type="button"
            className={`dsp-sfs-tab${active ? ' active' : ''}`}
            onClick={() => onFilterChange(tab.key)}
          >
            {tab.dot && (
              <span className="dsp-sfs-dot" style={{ background: tab.dot }} />
            )}
            <span>{tab.label}</span>
            <span className="dsp-sfs-count">{count}</span>
          </button>
        );
      })}
    </div>
  );
}
