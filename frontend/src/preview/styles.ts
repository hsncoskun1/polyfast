/**
 * Sidebar Preview — design tokens + ensureStyles helper + tone maps
 *
 * Kapsam (kucuk omurga):
 * - COLOR / FONT / SIZE tokens
 * - ensureStyles (tek style[data-dsp-styles] element)
 * - PNL_TONE / RULE_TONE / ACTIVITY_TONE / HEALTH_TONE tone map'leri
 *
 * Coin metadata fallback BURADA DEGIL — `coinRegistry.ts` icinde.
 *
 * Reusable disiplin: bu dosya ileride tasinabilir, baska preview'lar
 * da kullanabilir.
 */

import type {
  PnlTone,
  ActivitySeverity,
  RuleStateContract,
  HealthLiteral,
} from '../api/dashboard';

// ╔══════════════════════════════════════════════════════════════╗
// ║  COLOR TOKENS                                                ║
// ╚══════════════════════════════════════════════════════════════╝

export const COLOR = {
  // Background tonlari (turn 4: siyah -> hafif mor tint)
  bg: '#0a0612',
  bgRaised: '#0f0a1b',
  surface: '#140e22',
  surfaceHover: '#1a1429',
  border: 'rgba(139, 92, 246, 0.18)',
  borderStrong: 'rgba(139, 92, 246, 0.34)',
  divider: 'rgba(139, 92, 246, 0.12)',

  // Brand
  brand: '#8b5cf6', // mor marka aksanI
  brandSoft: 'rgba(139, 92, 246, 0.18)',
  brandGlow: 'rgba(139, 92, 246, 0.42)',

  // Semantik renkler
  green: '#22c55e', // aktif / kar / pass
  greenSoft: 'rgba(34, 197, 94, 0.16)',
  greenGlow: 'rgba(34, 197, 94, 0.34)',

  red: '#ef4444', // zarar / risk / fail
  redSoft: 'rgba(239, 68, 68, 0.16)',
  redGlow: 'rgba(239, 68, 68, 0.34)',

  yellow: '#eab308', // bekleme / uyari / waiting
  yellowSoft: 'rgba(234, 179, 8, 0.16)',
  yellowGlow: 'rgba(234, 179, 8, 0.34)',

  cyan: '#06b6d4', // pasif / soft / unknown
  cyanSoft: 'rgba(6, 182, 212, 0.16)',
  cyanGlow: 'rgba(6, 182, 212, 0.34)',

  // Metinler
  text: '#e2e2eb',
  textMuted: '#7e7e92',
  textDim: '#54546a',
  textOff: '#3a3a4a',
} as const;

// ╔══════════════════════════════════════════════════════════════╗
// ║  FONT TOKENS                                                 ║
// ╚══════════════════════════════════════════════════════════════╝

export const FONT = {
  sans: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif',
  mono: '"JetBrains Mono", "Fira Code", "Cascadia Code", Consolas, monospace',

  size: {
    xs: '10px',
    sm: '11px',
    md: '12px',
    lg: '14px',
    xl: '16px',
    xxl: '20px',
    huge: '24px',
  },

  weight: {
    normal: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
  },
} as const;

// ╔══════════════════════════════════════════════════════════════╗
// ║  SIZE / LAYOUT TOKENS                                        ║
// ╚══════════════════════════════════════════════════════════════╝

export const SIZE = {
  sidebarWidth: 252, // 240 -> 252 (turn 2: ferah brand+nav+bot panel)
  topBarHeight: 84, // 76 -> 84 (turn 2: KPI rakamlar buyutuldu)
  sectionStripHeight: 44, // 40 -> 44 (turn 3: filter strip gorunurluk)
  tileMinHeight: 96,
  radius: 6,
  radiusLg: 10,
} as const;

// ╔══════════════════════════════════════════════════════════════╗
// ║  SECTION TONE                                                ║
// ╚══════════════════════════════════════════════════════════════╝

/**
 * 3 ana section'in tone'u — header + empty state + count badge.
 * Karar: Acik=green, Aranan=brand(mor), Aranmayan=cyan.
 */
export type SectionKey = 'open' | 'search' | 'idle';

export const SECTION_TONE: Record<
  SectionKey,
  {
    fg: string;
    bg: string;
    border: string;
    glow: string;
    title: string;
    subtitle: string;
  }
> = {
  open: {
    fg: COLOR.green,
    bg: COLOR.greenSoft,
    border: COLOR.greenSoft,
    glow: COLOR.greenGlow,
    title: 'AÇIK İŞLEMLER',
    subtitle: 'Açık pozisyonlar ve claim bekleyenler',
  },
  search: {
    fg: COLOR.brand,
    bg: COLOR.brandSoft,
    border: COLOR.borderStrong,
    glow: COLOR.brandGlow,
    title: 'İŞLEM ARANANLAR',
    subtitle: 'Sinyal bekleyen coinler',
  },
  idle: {
    fg: COLOR.cyan,
    bg: COLOR.cyanSoft,
    border: COLOR.cyanSoft,
    glow: COLOR.cyanGlow,
    title: 'İŞLEM ARANMAYANLAR',
    subtitle: 'Pasif veya kural beklenen coinler',
  },
};

// ╔══════════════════════════════════════════════════════════════╗
// ║  TONE MAPS                                                   ║
// ╚══════════════════════════════════════════════════════════════╝

/**
 * PnL renk tonu — profit/loss/neutral/pending/off → COLOR.
 * Tile sol kolon, KPI strip, summary kullanir.
 */
export const PNL_TONE: Record<
  PnlTone,
  { fg: string; bg: string; glow: string }
> = {
  profit: { fg: COLOR.green, bg: COLOR.greenSoft, glow: COLOR.greenGlow },
  loss: { fg: COLOR.red, bg: COLOR.redSoft, glow: COLOR.redGlow },
  neutral: { fg: COLOR.text, bg: COLOR.surface, glow: 'transparent' },
  pending: { fg: COLOR.yellow, bg: COLOR.yellowSoft, glow: COLOR.yellowGlow },
  off: { fg: COLOR.textDim, bg: 'transparent', glow: 'transparent' },
};

/**
 * Rule visual state — pass/fail/waiting/disabled → COLOR.
 * RuleBlock kullanir.
 */
export const RULE_TONE: Record<
  RuleStateContract,
  { fg: string; bg: string; border: string }
> = {
  pass: { fg: COLOR.green, bg: COLOR.greenSoft, border: COLOR.greenSoft },
  fail: { fg: COLOR.red, bg: COLOR.redSoft, border: COLOR.redSoft },
  waiting: {
    fg: COLOR.yellow,
    bg: COLOR.yellowSoft,
    border: COLOR.yellowSoft,
  },
  disabled: { fg: COLOR.textDim, bg: 'transparent', border: COLOR.divider },
};

/**
 * Activity bildirimi severity → COLOR.
 * ActivityStatusLine kullanir.
 */
export const ACTIVITY_TONE: Record<ActivitySeverity, { fg: string; dot: string }> = {
  success: { fg: COLOR.green, dot: COLOR.green },
  warning: { fg: COLOR.yellow, dot: COLOR.yellow },
  error: { fg: COLOR.red, dot: COLOR.red },
  info: { fg: COLOR.text, dot: COLOR.brand },
  pending: { fg: COLOR.yellow, dot: COLOR.yellow },
  off: { fg: COLOR.textDim, dot: COLOR.textDim },
};

/**
 * Health (BotStatusContract.health) → label + color.
 * HealthIndicator kullanir.
 * Kural: unknown = cyan (product_health_indicator.md)
 */
export const HEALTH_TONE: Record<HealthLiteral, { label: string; fg: string; dot: string }> = {
  healthy: { label: 'Bağlantı OK', fg: COLOR.green, dot: COLOR.green },
  degraded: { label: 'Kısıtlı', fg: COLOR.yellow, dot: COLOR.yellow },
  critical: { label: 'Hatası', fg: COLOR.red, dot: COLOR.red },
  unknown: { label: 'Bilinmiyor', fg: COLOR.cyan, dot: COLOR.cyan },
};

// ╔══════════════════════════════════════════════════════════════╗
// ║  ensureStyles helper                                         ║
// ╚══════════════════════════════════════════════════════════════╝

/**
 * CSS-in-JS injection helper.
 *
 * Tek bir <style data-dsp-styles> element olusturur, key bazinda CSS
 * blogu ekler. Ayni key tekrar gelirse override eder. SSR/test guvenli.
 *
 * Kullanim:
 *   ensureStyles('sidebar', `.dsp-sidebar { ... }`);
 *
 * NOT: 1. tur kompakt baslangicI icin component'ler kendi CSS'ini
 * inject eder. Ileride tek stylesheet'e tasinacak (CSS konsolidasyon
 * adimi, sonraki tur).
 */
const _injected = new Set<string>();

export function ensureStyles(key: string, css: string): void {
  if (typeof document === 'undefined') return;
  if (_injected.has(key)) return;
  _injected.add(key);

  let el = document.querySelector<HTMLStyleElement>('style[data-dsp-styles]');
  if (!el) {
    el = document.createElement('style');
    el.setAttribute('data-dsp-styles', '');
    document.head.appendChild(el);
  }
  el.appendChild(document.createTextNode(`/* ${key} */\n${css}\n`));
}
