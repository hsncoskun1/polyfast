/**
 * mockData — sidebar preview showcase modu icin tum activity senaryolarini
 * tek ekranda gosteren genis mock veri seti.
 *
 * Erisim: localhost:5173/?preview=sidebar&mock=full
 *
 * Kurallar:
 * - Backend contract surface (api/dashboard.ts) ile birebir tip uyumlu
 * - Gercek mod (?preview=sidebar) bu dosyayi YUKLEMEZ
 * - 19 anlamli activity senaryosu (her biri farkli mesaj/severity/state)
 * - Onceki session'daki 64 unique activity'den damitilan ana senaryolar:
 *
 *   OPEN (7): yeni fill, TP yaklasiyor, TP closed, SL yaklasiyor,
 *             SL closed, FS countdown, FS closed
 *   CLAIM (3): pending RETRY, OK, FAIL
 *   SEARCH (6): sinyal hazir, FOK dolum, Delta wait, Spread fail,
 *               Bot max, Balance yetersiz
 *   IDLE (3): aktif et, ayar gir, error
 */

import type {
  HealthResponse,
  DashboardOverview,
  PositionSummary,
  ClaimSummary,
  SearchTileContract,
  IdleTileContract,
  CoinInfoContract,
  RuleSpecContract,
} from '../api/dashboard';

// ╔══════════════════════════════════════════════════════════════╗
// ║  Sidebar bot status — canli session                          ║
// ╚══════════════════════════════════════════════════════════════╝

export const MOCK_HEALTH: HealthResponse = {
  status: 'ok',
  version: '0.8.0',
  uptime_seconds: 18367,
  components: {},
  bot_status: {
    running: true,
    health: 'healthy',
    restore_phase: false,
    shutdown_in_progress: false,
    startup_guard_blocked: false,
    paused: false,
    uptime_sec: 18367,
    latency_ms: 47,
  },
};

// ╔══════════════════════════════════════════════════════════════╗
// ║  Top bar overview — dolu KPI strip                           ║
// ╚══════════════════════════════════════════════════════════════╝

export const MOCK_OVERVIEW: DashboardOverview = {
  trading_enabled: true,
  balance: { available: 1036.42, total: 1247.85, is_stale: false, age_seconds: 1.2 },
  open_positions: 7,
  pending_claims: 3,
  session_trade_count: 19,
  configured_coins: 9,
  eligible_coins: 6,
  bot_status: MOCK_HEALTH.bot_status,
  bakiye_text: '$1,247.85',
  kullanilabilir_text: '$1,036.42',
  session_pnl: 12.34,
  session_pnl_pct: 1.05,
  acilan: 19,
  gorulen: 248,
  ag_rate: '7.7%',
  win: 13,
  lost: 6,
  winrate: '68.4%',
};

// ╔══════════════════════════════════════════════════════════════╗
// ║  Coin metadata                                               ║
// ╚══════════════════════════════════════════════════════════════╝

export const MOCK_COINS: CoinInfoContract[] = [
  { symbol: 'BTC',   display_name: 'Bitcoin',   configured: true,  enabled: true,  trade_eligible: true,  side_mode: 'both', order_amount: 5 },
  { symbol: 'ETH',   display_name: 'Ethereum',  configured: true,  enabled: true,  trade_eligible: true,  side_mode: 'both', order_amount: 3 },
  { symbol: 'SOL',   display_name: 'Solana',    configured: true,  enabled: true,  trade_eligible: true,  side_mode: 'both', order_amount: 2 },
  { symbol: 'DOGE',  display_name: 'Dogecoin',  configured: true,  enabled: true,  trade_eligible: true,  side_mode: 'both', order_amount: 2 },
  { symbol: 'XRP',   display_name: 'Ripple',    configured: true,  enabled: false, trade_eligible: false, side_mode: 'both', order_amount: 2 },
  { symbol: 'ADA',   display_name: 'Cardano',   configured: false, enabled: false, trade_eligible: false, side_mode: 'both', order_amount: 0 },
  { symbol: 'AVAX',  display_name: 'Avalanche', configured: true,  enabled: true,  trade_eligible: true,  side_mode: 'both', order_amount: 2 },
  { symbol: 'LINK',  display_name: 'Chainlink', configured: true,  enabled: true,  trade_eligible: true,  side_mode: 'both', order_amount: 2 },
  { symbol: 'MATIC', display_name: 'Polygon',   configured: true,  enabled: true,  trade_eligible: true,  side_mode: 'both', order_amount: 2 },
  { symbol: 'BNB',   display_name: 'BNB',       configured: true,  enabled: true,  trade_eligible: true,  side_mode: 'both', order_amount: 3 },
];

// ╔══════════════════════════════════════════════════════════════╗
// ║  Helper — base position template                             ║
// ╚══════════════════════════════════════════════════════════════╝

const baseOpen = (id: string, asset: string, side: 'UP' | 'DOWN'): PositionSummary => ({
  position_id: id,
  asset,
  side,
  state: 'open_confirmed',
  fill_price: 0.65,
  requested_amount_usd: 2.0,
  net_position_shares: 3.07,
  close_reason: null,
  net_realized_pnl: 0,
  created_at: '2026-04-07T14:00:00Z',
  variant: 'open',
});

const baseClaim = (id: string, asset: string): PositionSummary => ({
  position_id: id,
  asset,
  side: 'UP',
  state: 'closed',
  fill_price: 0.65,
  requested_amount_usd: 2.0,
  net_position_shares: 3.07,
  close_reason: 'expiry',
  net_realized_pnl: 0,
  created_at: '2026-04-07T13:30:00Z',
  variant: 'claim',
  live: null,
  exits: null,
});

// ╔══════════════════════════════════════════════════════════════╗
// ║  POSITIONS — 10 tile (7 open + 3 claim)                      ║
// ║  Open lifecycle: yeni fill -> TP appr -> TP closed,          ║
// ║                 SL appr -> SL closed, FS countdown -> FS closed
// ║  Claim lifecycle: pending RETRY, OK, FAIL                    ║
// ╚══════════════════════════════════════════════════════════════╝

export const MOCK_POSITIONS: PositionSummary[] = [
  // ─── OPEN LIFECYCLE 1: yeni fill ───
  // 1) BTC — yeni fill (pozisyon yeni acildi)
  {
    ...baseOpen('mock-pos-1', 'BTC', 'UP'),
    fill_price: 0.68,
    pnl_big: '0.0%',
    pnl_amount: '0.00$',
    pnl_tone: 'neutral',
    live: { side: 'UP', entry: '68', live: '68', delta_text: '0' },
    exits: { tp: '74', sl: '62', fs: '5:00', fs_pnl: '-5%' },
    activity: { text: 'Emir doldu | UP 68, pozisyon açıldı', severity: 'success' },
  },

  // ─── OPEN LIFECYCLE 2: TP yaklasiyor ───
  // 2) ETH — TP yaklasiyor
  {
    ...baseOpen('mock-pos-2', 'ETH', 'UP'),
    fill_price: 0.83,
    pnl_big: '+3.1%',
    pnl_amount: '+0.31$',
    pnl_tone: 'profit',
    live: { side: 'UP', entry: '83', live: '86', delta_text: '+3' },
    exits: { tp: '87', sl: '81', fs: '2:14', fs_pnl: '-5%' },
    activity: { text: 'TP yaklaşıyor | hedef 87', severity: 'success' },
  },

  // ─── OPEN LIFECYCLE 3: TP closed (positif kapali ama henuz claim olmamis) ───
  // 3) AVAX — TP tetiklendi
  {
    ...baseOpen('mock-pos-3', 'AVAX', 'UP'),
    fill_price: 0.78,
    pnl_big: '+13.4%',
    pnl_amount: '+1.34$',
    pnl_tone: 'profit',
    live: { side: 'UP', entry: '78', live: '89', delta_text: '+11' },
    exits: { tp: '88', sl: '72', fs: '0:42', fs_pnl: '-5%' },
    activity: { text: 'TP @ 88 | +1.34$ kapatma emri gönderildi', severity: 'success' },
  },

  // ─── OPEN LIFECYCLE 4: SL yaklasiyor ───
  // 4) SOL — SL yaklasiyor
  {
    ...baseOpen('mock-pos-4', 'SOL', 'DOWN'),
    fill_price: 0.55,
    pnl_big: '-2.4%',
    pnl_amount: '-0.18$',
    pnl_tone: 'loss',
    live: { side: 'DOWN', entry: '55', live: '53', delta_text: '-2' },
    exits: { tp: '60', sl: '52', fs: '1:48', fs_pnl: '-5%' },
    activity: { text: 'SL yaklaşıyor | Limit 52', severity: 'warning' },
  },

  // ─── OPEN LIFECYCLE 5: SL tetiklendi ───
  // 5) DOGE — SL tetiklendi
  {
    ...baseOpen('mock-pos-5', 'DOGE', 'UP'),
    fill_price: 0.71,
    pnl_big: '-15.0%',
    pnl_amount: '-0.30$',
    pnl_tone: 'loss',
    live: { side: 'UP', entry: '71', live: '56', delta_text: '-15' },
    exits: { tp: '76', sl: '56', fs: '0:18', fs_pnl: '-5%' },
    activity: { text: 'SL tetiklendi | -0.24$ satış emri gönderildi', severity: 'error' },
  },

  // ─── OPEN LIFECYCLE 6: FS (zaman) sebep — countdown ───
  // 6) LINK — FS countdown (zaman tetikleyici)
  {
    ...baseOpen('mock-pos-6', 'LINK', 'DOWN'),
    fill_price: 0.62,
    pnl_big: '-1.8%',
    pnl_amount: '-0.04$',
    pnl_tone: 'loss',
    live: { side: 'DOWN', entry: '62', live: '64', delta_text: '+2' },
    exits: { tp: '67', sl: '58', fs: '0:08', fs_pnl: '-5%' },
    activity: { text: 'FS countdown | süre 8s, zorunlu kapatma yaklaşıyor', severity: 'pending' },
  },

  // ─── OPEN LIFECYCLE 7: FSP (eşik) sebep — FS başladı ───
  // 7) BNB — FSP tetik (PnL eşiği aşıldı, force sell başladı)
  {
    ...baseOpen('mock-pos-7', 'BNB', 'UP'),
    fill_price: 0.56,
    pnl_big: '-5.1%',
    pnl_amount: '-0.10$',
    pnl_tone: 'loss',
    live: { side: 'UP', entry: '56', live: '50', delta_text: '-6' },
    exits: { tp: '61', sl: '51', fs: '1:05', fs_pnl: '-5%' },
    activity: { text: 'FS eşik aşıldı | -5.1% zorunlu kapatma başladı', severity: 'error' },
  },

  // ─── OPEN LIFECYCLE 8: FS kapandı ───
  // 8) XRP — Force sell ile kapandı
  {
    ...baseOpen('mock-pos-fs-closed', 'XRP', 'DOWN'),
    fill_price: 0.44,
    pnl_big: '-4.8%',
    pnl_amount: '-0.09$',
    pnl_tone: 'loss',
    live: { side: 'DOWN', entry: '44', live: '50', delta_text: '+6' },
    exits: { tp: '39', sl: '48', fs: '0:00', fs_pnl: '-5%' },
    activity: { text: 'FS @ 50 | -0.09$ Force sell ile kapandı', severity: 'warning' },
  },

  // ─── OPEN LIFECYCLE 9: Sakin kar ───
  // 9) ADA — normal akış, kar bölgesi, hiçbir tetik yakın değil
  {
    ...baseOpen('mock-pos-calm-profit', 'ADA', 'UP'),
    fill_price: 0.72,
    pnl_big: '+4.2%',
    pnl_amount: '+0.42$',
    pnl_tone: 'profit',
    live: { side: 'UP', entry: '72', live: '75', delta_text: '+3' },
    exits: { tp: '80', sl: '67', fs: '3:22', fs_pnl: '-5%' },
    activity: { text: 'Pozisyon açık | hedefe doğru', severity: 'info' },
  },

  // ─── OPEN LIFECYCLE 10: Sakin zarar ───
  // 10) DOT — normal akış, hafif zarar, tetikler uzak
  {
    ...baseOpen('mock-pos-calm-loss', 'DOT', 'DOWN'),
    fill_price: 0.58,
    pnl_big: '-2.1%',
    pnl_amount: '-0.21$',
    pnl_tone: 'loss',
    live: { side: 'DOWN', entry: '58', live: '56', delta_text: '-2' },
    exits: { tp: '63', sl: '54', fs: '2:45', fs_pnl: '-5%' },
    activity: { text: 'Pozisyon açık | dalgalanıyor', severity: 'info' },
  },

  // ─── CLAIM LIFECYCLE 1: pending RETRY ───
  // 8) XRP — Claim bekliyor (RETRY)
  {
    ...baseClaim('mock-pos-8', 'XRP'),
    pnl_big: 'CLAIM',
    pnl_amount: 'PENDING',
    pnl_tone: 'pending',
    activity: { text: 'Claim bekliyor | tamamlanmadan yeni işlem açılamaz', severity: 'pending' },
  },

  // ─── CLAIM LIFECYCLE 2: OK ───
  // 9) ADA — Claim basarili
  {
    ...baseClaim('mock-pos-9', 'ADA'),
    net_realized_pnl: 0.42,
    pnl_big: 'CLAIM',
    pnl_amount: '+0.42$',
    pnl_tone: 'profit',
    activity: { text: 'Claim başarılı | $4.21 hesaba aktarıldı', severity: 'success' },
  },

  // ─── CLAIM LIFECYCLE 3: FAIL ───
  // 10) MATIC — Claim basarisiz
  {
    ...baseClaim('mock-pos-10', 'MATIC'),
    net_realized_pnl: -2.0,
    pnl_big: 'MAX DENEME',
    pnl_amount: '-2.00$',
    pnl_tone: 'loss',
    activity: { text: 'Max retry | manuel müdahale gerek', severity: 'error' },
  },
];

// ╔══════════════════════════════════════════════════════════════╗
// ║  Claims — 3 lifecycle ile eslesme                            ║
// ╚══════════════════════════════════════════════════════════════╝

export const MOCK_CLAIMS: ClaimSummary[] = [
  // XRP RETRY
  {
    claim_id: 'mock-claim-1',
    asset: 'XRP',
    position_id: 'mock-pos-8',
    claim_status: 'pending',
    outcome: 'pending',
    claimed_amount_usdc: 0,
    retry_count: 3,
    status: 'RETRY',
    retry: 3,
    max_retry: 20,
    next_sec: 20,
    payout: null,
  },
  // ADA OK
  {
    claim_id: 'mock-claim-2',
    asset: 'ADA',
    position_id: 'mock-pos-9',
    claim_status: 'success',
    outcome: 'redeemed_won',
    claimed_amount_usdc: 4.21,
    retry_count: 1,
    status: 'OK',
    retry: 1,
    max_retry: 20,
    next_sec: null,
    payout: '$4.21',
  },
  // MATIC FAIL
  {
    claim_id: 'mock-claim-3',
    asset: 'MATIC',
    position_id: 'mock-pos-10',
    claim_status: 'failed',
    outcome: 'lost',
    claimed_amount_usdc: 0,
    retry_count: 20,
    status: 'FAIL',
    retry: 20,
    max_retry: 20,
    next_sec: null,
    payout: null,
  },
];

// ╔══════════════════════════════════════════════════════════════╗
// ║  Search — 6 tile (sinyal lifecycle)                          ║
// ╚══════════════════════════════════════════════════════════════╝

const allPass = (zaman = '3:15', fiyat = '83', delta = '$55', spread = '1.8%'): RuleSpecContract[] => [
  { label: 'Zaman',  live_value: zaman,  threshold_text: '30-270s', state: 'pass' },
  { label: 'Fiyat',  live_value: fiyat,  threshold_text: '≥ 80',    state: 'pass' },
  { label: 'Delta',  live_value: delta,  threshold_text: '≥ $50',   state: 'pass' },
  { label: 'Spread', live_value: spread, threshold_text: '≤ 3%',    state: 'pass' },
  { label: 'EvMax',  live_value: '0/1',  threshold_text: '1',       state: 'pass' },
  { label: 'BotMax', live_value: '2/3',  threshold_text: '3',       state: 'pass' },
];

export const MOCK_SEARCH: SearchTileContract[] = [
  // ─── SEARCH 1: sinyal hazir + FOK gonderiliyor ───
  // 11) BTC — Sinyal hazir
  {
    tile_id: 'mock-search-1',
    coin: 'BTC',
    event_url: 'https://polymarket.com/event/btc-search',
    pnl_big: '6/6',
    pnl_amount: 'HAZIR',
    pnl_tone: 'profit',
    ptb: '111,234',
    live: '111,289',
    delta: '$55',
    rules: allPass(),
    activity: { text: 'Sinyal hazır | UP 56 gönderiliyor', severity: 'success' },
    signal_ready: true,
    type: 'ok',
  },

  // ─── SEARCH 2: FOK dolum bekliyor ───
  // 12) ETH — FOK dolum
  {
    tile_id: 'mock-search-2',
    coin: 'ETH',
    event_url: 'https://polymarket.com/event/eth-search',
    pnl_big: '6/6',
    pnl_amount: 'EMIR',
    pnl_tone: 'profit',
    ptb: '3,820',
    live: '3,876',
    delta: '$56',
    rules: allPass('2:48', '78', '$56', '2.1%'),
    activity: { text: 'UP 56 emir gönderildi | dolum bekleniyor', severity: 'info' },
    signal_ready: true,
    type: 'wait',
  },

  // ─── SEARCH 3: Delta yetersiz ───
  // 13) SOL — Delta wait
  {
    tile_id: 'mock-search-3',
    coin: 'SOL',
    event_url: 'https://polymarket.com/event/sol-search',
    pnl_big: '4/6',
    pnl_amount: 'BEKLE',
    pnl_tone: 'pending',
    ptb: '241.56',
    live: '240.83',
    delta: '$32',
    rules: [
      { label: 'Zaman',  live_value: '2:44', threshold_text: '30-270s', state: 'pass' },
      { label: 'Fiyat',  live_value: '241',  threshold_text: '≥ 80',    state: 'pass' },
      { label: 'Delta',  live_value: '$32',  threshold_text: '≥ $50',   state: 'fail' },
      { label: 'Spread', live_value: '',     threshold_text: '≤ 3%',    state: 'waiting' },
      { label: 'EvMax',  live_value: '0/1',  threshold_text: '1',       state: 'pass' },
      { label: 'BotMax', live_value: '2/3',  threshold_text: '3',       state: 'pass' },
    ],
    activity: { text: 'Delta yetersiz | sinyal bekleniyor', severity: 'pending' },
    signal_ready: false,
    type: 'wait',
  },

  // ─── SEARCH 4: Spread yuksek ───
  // 14) DOGE — Spread fail
  {
    tile_id: 'mock-search-4',
    coin: 'DOGE',
    event_url: 'https://polymarket.com/event/doge-search',
    pnl_big: '4/6',
    pnl_amount: 'BEKLE',
    pnl_tone: 'pending',
    ptb: '0.162',
    live: '0.163',
    delta: '$78',
    rules: [
      { label: 'Zaman',  live_value: '4:18', threshold_text: '30-270s', state: 'pass' },
      { label: 'Fiyat',  live_value: '162',  threshold_text: '≥ 80',    state: 'pass' },
      { label: 'Delta',  live_value: '$78',  threshold_text: '≥ $50',   state: 'pass' },
      { label: 'Spread', live_value: '',     threshold_text: '≤ 3%',    state: 'disabled' },
      { label: 'EvMax',  live_value: '0/1',  threshold_text: '1',       state: 'pass' },
      { label: 'BotMax', live_value: '2/3',  threshold_text: '3',       state: 'pass' },
    ],
    activity: { text: 'Spread yüksek | bekleniyor', severity: 'warning' },
    signal_ready: false,
    type: 'wait',
  },

  // ─── SEARCH 5: Bot max doldu ───
  // 15) AVAX — Bot max
  {
    tile_id: 'mock-search-5',
    coin: 'AVAX',
    event_url: 'https://polymarket.com/event/avax-search',
    pnl_big: '5/6',
    pnl_amount: 'BEKLE',
    pnl_tone: 'pending',
    ptb: '38.42',
    live: '38.51',
    delta: '$72',
    rules: [
      { label: 'Zaman',  live_value: '0:48', threshold_text: '30-270s', state: 'pass' },
      { label: 'Fiyat',  live_value: '38',   threshold_text: '≥ 30',    state: 'pass' },
      { label: 'Delta',  live_value: '$72',  threshold_text: '≥ $50',   state: 'pass' },
      { label: 'Spread', live_value: '2.1%', threshold_text: '≤ 3%',    state: 'pass' },
      { label: 'EvMax',  live_value: '0/1',  threshold_text: '1',       state: 'pass' },
      { label: 'BotMax', live_value: '3/3',  threshold_text: '3',       state: 'fail' },
    ],
    activity: { text: 'Bot max doldu | bekleniyor', severity: 'error' },
    signal_ready: false,
    type: 'wait',
  },

  // ─── SEARCH 6: Balance yetersiz ───
  // 16) LINK — Balance yetersiz
  {
    tile_id: 'mock-search-6',
    coin: 'LINK',
    event_url: 'https://polymarket.com/event/link-search',
    pnl_big: '6/6',
    pnl_amount: 'HAZIR',
    pnl_tone: 'profit',
    ptb: '14.20',
    live: '14.31',
    delta: '$60',
    rules: allPass('1:30', '142', '$60', '1.9%'),
    activity: { text: 'Balance yetersiz | min $1.00', severity: 'error' },
    signal_ready: false,
    type: 'wait',
  },
];

// ╔══════════════════════════════════════════════════════════════╗
// ║  Idle — 3 tile                                               ║
// ╚══════════════════════════════════════════════════════════════╝

export const MOCK_IDLE: IdleTileContract[] = [
  // ─── IDLE 1: Aktif et ($) ───
  // 17) MATIC — Aktif etmek icin $
  {
    tile_id: 'mock-idle-1',
    coin: 'MATIC',
    idle_kind: 'bot_stopped',
    msg: 'Ayarlar yapıldı ama pasif durumda',
    activity: { text: 'Ayarlar yapıldı, aktif etmek için {DOLLAR} bas', severity: 'info' },
    rules: null,
    event_url: null,
  },

  // ─── IDLE 2: Ayar gir (⚙) ───
  // 18) BNB — Ayar girmek icin
  {
    tile_id: 'mock-idle-2',
    coin: 'BNB',
    idle_kind: 'waiting_rules',
    msg: 'Ayarlar tamamlanmadan coinde işlem açılamaz',
    activity: { text: 'Ayar girmek için {GEAR} butonuna bas', severity: 'off' },
    rules: [
      { label: 'Zaman',  live_value: '—', state: 'disabled' },
      { label: 'Fiyat',  live_value: '—', state: 'disabled' },
      { label: 'Delta',  live_value: '—', state: 'disabled' },
      { label: 'Spread', live_value: '—', state: 'disabled' },
      { label: 'EvMax',  live_value: '—', state: 'disabled' },
      { label: 'BotMax', live_value: '—', state: 'disabled' },
    ],
    event_url: null,
  },

  // ─── IDLE 3: error (PTB fetch hata) ───
  // 19) BTC — PTB fetch error
  {
    tile_id: 'mock-idle-3',
    coin: 'BTC',
    idle_kind: 'error',
    msg: 'PTB fetch hatası',
    activity: { text: 'Polymarket fiyat çekilemedi | son deneme: 30s önce', severity: 'error' },
    rules: null,
    event_url: null,
  },
];

// ╔══════════════════════════════════════════════════════════════╗
// ║  Tek noktadan export                                         ║
// ╚══════════════════════════════════════════════════════════════╝

/**
 * Toplam: 19 tile, 19 ayri activity senaryosu, tum severity/state/kind
 * varyantlarini kapsar.
 *
 * Section dagilimi:
 *  - ACIK ISLEMLER : 7 open + 3 claim = 10
 *  - ARANANLAR     : 6 search
 *  - ARANMAYANLAR  : 3 idle
 *  TOPLAM          : 19
 */
export const MOCK_DATA = {
  health: MOCK_HEALTH,
  overview: MOCK_OVERVIEW,
  positions: MOCK_POSITIONS,
  claims: MOCK_CLAIMS,
  search: MOCK_SEARCH,
  idle: MOCK_IDLE,
  coins: MOCK_COINS,
  loading: false,
  hasError: false,
  errorStreak: 0,
  lastSuccessAt: Date.now(),
} as const;
