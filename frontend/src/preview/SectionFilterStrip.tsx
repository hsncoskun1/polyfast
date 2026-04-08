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
  'sectionstrip-v3',
  `
.dsp-sfs {
  height: ${SIZE.sectionStripHeight}px;
  flex-shrink: 0;
  background: ${COLOR.bgRaised};
  border-bottom: 1px solid ${COLOR.border};
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 7px;
  font-family: ${FONT.sans};
}
.dsp-sfs-tab {
  flex: 1 1 0;
  justify-content: center;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: ${SIZE.radius}px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  font-size: 12.5px;
  font-weight: ${FONT.weight.semibold};
  color: ${COLOR.text};
  cursor: pointer;
  font-family: ${FONT.sans};
  white-space: nowrap;
  opacity: 0.78;
}
.dsp-sfs-tab:hover {
  opacity: 1;
  background: ${COLOR.surfaceHover};
}
.dsp-sfs-tab.active {
  opacity: 1;
  background: ${COLOR.brandSoft};
  border-color: ${COLOR.borderStrong};
  color: ${COLOR.text};
}
.dsp-sfs-tab .dsp-sfs-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dsp-sfs-tab .dsp-sfs-count {
  font-family: ${FONT.mono};
  font-size: 10.5px;
  font-weight: ${FONT.weight.bold};
  padding: 2px 8px;
  border-radius: 9px;
  background: ${COLOR.bgRaised};
  color: ${COLOR.text};
  min-width: 20px;
  text-align: center;
  border: 1px solid ${COLOR.divider};
}
.dsp-sfs-tab.active .dsp-sfs-count {
  background: ${COLOR.brand};
  color: ${COLOR.bg};
  border-color: ${COLOR.brand};
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
  { key: 'open', label: 'Açık İşlemler', dot: COLOR.green },
  { key: 'search', label: 'İşlem Aranan', dot: COLOR.brand },
  { key: 'idle', label: 'İşlem Aranmayan', dot: COLOR.cyan },
  { key: 'all', label: 'Tüm Marketler' },
];

export default function SectionFilterStrip({
  filter,
  onFilterChange,
  counts,
  only,
}: SectionFilterStripProps & { only?: SectionFilter[] }) {
  const tabs = only ? TABS.filter((t) => only.includes(t.key)) : TABS;
  return (
    <div className="dsp-sfs">
      {tabs.map((tab) => {
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
              <span
                className="dsp-sfs-dot"
                style={{
                  background: tab.dot,
                  boxShadow: `0 0 5px ${tab.dot}88`,
                }}
              />
            )}
            <span>{tab.label}</span>
            <span className="dsp-sfs-count">{count}</span>
          </button>
        );
      })}
    </div>
  );
}
