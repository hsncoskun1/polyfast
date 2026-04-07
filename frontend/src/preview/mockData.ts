/**
 * mockData — sidebar preview showcase modu icin tum state'leri gosteren
 * statik veri seti.
 *
 * Erisim: localhost:5173/?preview=sidebar&mock=full
 *
 * Kurallar:
 * - Backend contract surface (api/dashboard.ts) ile birebir tip uyumlu
 * - Gercek mod (`?preview=sidebar`) bu dosyayi YUKLEMEZ
 * - Test coplugu degil — anlamli 8 tile, her biri farkli bir senaryo
 * - 8 tile = 4 section x 2 ortalama varyant:
 *   AÇIK   : open profit, open loss, claim retry, claim success-like
 *   ARANAN : search ready, search wait
 *   PASIF  : idle manual off, idle no settings
 *
 * Showcase ek kazanim: top bar / sidebar bot status / health hepsi
 * canli gibi gorunsun (gercek bir trading session simulasyonu).
 *
 * Reusable: test, demo, future scenario'lar bu dosyadan yola cikabilir.
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

/**
 * Bot canli, healthy, 5sa+ uptime, 47ms latency.
 * Sidebar BotStatusPanel: NORMAL · Calisiyor · 5sa 06dk
 * HealthIndicator: Baglanti OK
 */
export const MOCK_HEALTH: HealthResponse = {
  status: 'ok',
  version: '0.8.0',
  uptime_seconds: 18367, // 5sa 06dk
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

/**
 * Top bar 3 grup KPI'lari canli session simulasyonu:
 *  - MONEY    : Bakiye $1,247.85 / Kullanilabilir $1,036.42 / Oturum PnL +$48.12 (+4.07%)
 *  - ACTIVITY : Acilan 12 / Gorulen 248 / A/G 4.8%
 *  - OUTCOME  : Win 8 / Lost 4 / Bekleyen 2 / Winrate 66.7%
 */
export const MOCK_OVERVIEW: DashboardOverview = {
  // Legacy
  trading_enabled: true,
  balance: {
    available: 1036.42,
    total: 1247.85,
    is_stale: false,
    age_seconds: 1.2,
  },
  open_positions: 2, // BTC + ETH (claim ayri)
  pending_claims: 2, // SOL retry + DOGE success
  session_trade_count: 12,
  configured_coins: 9,
  eligible_coins: 6,
  // Extended
  bot_status: MOCK_HEALTH.bot_status,
  bakiye_text: '$1,247.85',
  kullanilabilir_text: '$1,036.42',
  session_pnl: 48.12,
  session_pnl_pct: 4.07,
  acilan: 12,
  gorulen: 248,
  ag_rate: '4.8%',
  win: 8,
  lost: 4,
  winrate: '66.7%',
};

// ╔══════════════════════════════════════════════════════════════╗
// ║  Coin metadata                                               ║
// ╚══════════════════════════════════════════════════════════════╝

/**
 * Backend `/api/dashboard/coins` simulasyonu.
 * Frontend lookupCoin() bu listede arar, bulamazsa coinRegistry
 * fallback'e duser. Showcase'de tum sembolleri buraya koyduk ki
 * backend wiring olmadan da tam metadata gozuksun.
 */
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
// ║  Positions — open + claim variant'lar                        ║
// ╚══════════════════════════════════════════════════════════════╝

/**
 * 4 position kaydi:
 *  1. BTC open profit  — TP yaklasiyor (yesil activity)
 *  2. ETH open loss    — SL yaklasiyor (kirmizi activity)
 *  3. SOL claim RETRY  — payout claim ediliyor (sari activity)
 *  4. DOGE claim OK    — claim basarili (yesil activity)
 *
 * NOT: ClaimStatusPanel su an PositionSummary uzerinden status
 * almiyor, claims listesinden lookup yapacak (sonraki tur). Bu
 * mock'ta her ikisini de doldurduk ki gorunum tam olsun.
 */
export const MOCK_POSITIONS: PositionSummary[] = [
  // 1) BTC — open profit
  {
    position_id: 'mock-btc-open-1',
    asset: 'BTC',
    side: 'UP',
    state: 'open_confirmed',
    fill_price: 0.83,
    requested_amount_usd: 5.0,
    net_position_shares: 6.02,
    close_reason: null,
    net_realized_pnl: 0,
    created_at: '2026-04-07T13:55:00Z',
    variant: 'open',
    live: { side: 'UP', entry: '83', live: '85.6', delta_text: '+2.6' },
    exits: { tp: '87', sl: '81', fs: '30s', fs_pnl: '-5%' },
    pnl_big: '+3.1%',
    pnl_amount: '+0.31$',
    pnl_tone: 'profit',
    activity: {
      text: 'TP yaklaşıyor — hedef 87',
      severity: 'success',
    },
    event_url: 'https://polymarket.com/event/bitcoin-up-or-down-5-min',
  },

  // 2) ETH — open loss
  {
    position_id: 'mock-eth-open-2',
    asset: 'ETH',
    side: 'DOWN',
    state: 'open_confirmed',
    fill_price: 0.55,
    requested_amount_usd: 3.0,
    net_position_shares: 5.45,
    close_reason: null,
    net_realized_pnl: 0,
    created_at: '2026-04-07T13:57:00Z',
    variant: 'open',
    live: { side: 'DOWN', entry: '55', live: '52.8', delta_text: '-2.2' },
    exits: { tp: '60', sl: '52', fs: '30s', fs_pnl: '-5%' },
    pnl_big: '-2.4%',
    pnl_amount: '-0.18$',
    pnl_tone: 'loss',
    activity: {
      text: 'SL yaklaşıyor — Limit 52',
      severity: 'error',
    },
    event_url: 'https://polymarket.com/event/ethereum-up-or-down-5-min',
  },

  // 3) SOL — claim retry
  {
    position_id: 'mock-sol-claim-3',
    asset: 'SOL',
    side: 'UP',
    state: 'closed',
    fill_price: 0.62,
    requested_amount_usd: 2.0,
    net_position_shares: 3.21,
    close_reason: 'expiry',
    net_realized_pnl: 0,
    created_at: '2026-04-07T13:48:00Z',
    variant: 'claim',
    live: null,
    exits: null,
    pnl_big: null,
    pnl_amount: null,
    pnl_tone: 'pending',
    activity: {
      text: 'Pozisyon resolved — payout claim ediliyor',
      severity: 'warning',
    },
    event_url: 'https://polymarket.com/event/solana-up-or-down-5-min',
  },

  // 4) DOGE — claim success-like
  {
    position_id: 'mock-doge-claim-4',
    asset: 'DOGE',
    side: 'UP',
    state: 'closed',
    fill_price: 0.71,
    requested_amount_usd: 2.0,
    net_position_shares: 2.81,
    close_reason: 'expiry',
    net_realized_pnl: 0.42,
    created_at: '2026-04-07T13:42:00Z',
    variant: 'claim',
    live: null,
    exits: null,
    pnl_big: '+21.0%',
    pnl_amount: '+0.42$',
    pnl_tone: 'profit',
    activity: {
      text: 'Claim başarılı — $4.21 hesaba aktarıldı',
      severity: 'success',
    },
    event_url: 'https://polymarket.com/event/dogecoin-up-or-down-5-min',
  },

  // 5) AVAX — open profit (TP tetiklendi)
  {
    position_id: 'mock-avax-open-5',
    asset: 'AVAX',
    side: 'UP',
    state: 'open_confirmed',
    fill_price: 0.78,
    requested_amount_usd: 2.0,
    net_position_shares: 2.56,
    close_reason: null,
    net_realized_pnl: 0,
    created_at: '2026-04-07T14:01:00Z',
    variant: 'open',
    live: { side: 'UP', entry: '78', live: '88.5', delta_text: '+10.5' },
    exits: { tp: '88', sl: '72', fs: '14s', fs_pnl: '-5%' },
    pnl_big: '+13.4%',
    pnl_amount: '+1.34$',
    pnl_tone: 'profit',
    activity: {
      text: '● TP tetiklendi — kapatma emri gönderildi',
      severity: 'success',
    },
    event_url: 'https://polymarket.com/event/avax-up-or-down-5-min',
  },

  // 6) LINK — open loss (FS countdown)
  {
    position_id: 'mock-link-open-6',
    asset: 'LINK',
    side: 'DOWN',
    state: 'open_confirmed',
    fill_price: 0.62,
    requested_amount_usd: 2.0,
    net_position_shares: 3.22,
    close_reason: null,
    net_realized_pnl: 0,
    created_at: '2026-04-07T13:59:30Z',
    variant: 'open',
    live: { side: 'DOWN', entry: '62', live: '64.2', delta_text: '+2.2' },
    exits: { tp: '67', sl: '58', fs: '8s', fs_pnl: '-5%' },
    pnl_big: '-1.8%',
    pnl_amount: '-0.04$',
    pnl_tone: 'loss',
    activity: {
      text: '⏱ FS countdown — 8 saniye sonra zorunlu kapatma',
      severity: 'pending',
    },
    event_url: 'https://polymarket.com/event/link-up-or-down-5-min',
  },

  // 7) MATIC — claim FAIL
  {
    position_id: 'mock-matic-claim-7',
    asset: 'MATIC',
    side: 'DOWN',
    state: 'closed',
    fill_price: 0.55,
    requested_amount_usd: 2.0,
    net_position_shares: 3.64,
    close_reason: 'expiry',
    net_realized_pnl: -2.0,
    created_at: '2026-04-07T13:35:00Z',
    variant: 'claim',
    live: null,
    exits: null,
    pnl_big: '-100%',
    pnl_amount: '-2.00$',
    pnl_tone: 'loss',
    activity: {
      text: '✕ Claim başarısız — 5/5 retry doldu, manuel müdahale gerek',
      severity: 'error',
    },
    event_url: 'https://polymarket.com/event/matic-up-or-down-5-min',
  },
];

// ╔══════════════════════════════════════════════════════════════╗
// ║  Claims — backend ClaimSummary lookup mock'u                 ║
// ╚══════════════════════════════════════════════════════════════╝

/**
 * Iki claim kaydi (SOL retry + DOGE OK).
 * EventTile claim variant'i ileride bu listeden lookup yapacak.
 * Su an PositionSummary uzerinden render ediliyor, ama ClaimSummary
 * mock'u backend contract uyumu icin hazir.
 */
export const MOCK_CLAIMS: ClaimSummary[] = [
  {
    claim_id: 'mock-claim-sol-1',
    asset: 'SOL',
    position_id: 'mock-sol-claim-3',
    claim_status: 'pending',
    outcome: 'pending',
    claimed_amount_usdc: 0,
    retry_count: 3,
    status: 'RETRY',
    retry: 3,
    max_retry: 5,
    next_sec: 20,
    payout: null,
  },
  {
    claim_id: 'mock-claim-doge-1',
    asset: 'DOGE',
    position_id: 'mock-doge-claim-4',
    claim_status: 'success',
    outcome: 'redeemed_won',
    claimed_amount_usdc: 4.21,
    retry_count: 1,
    status: 'OK',
    retry: 1,
    max_retry: 5,
    next_sec: null,
    payout: '$4.21',
  },
  // MATIC claim FAIL
  {
    claim_id: 'mock-claim-matic-1',
    asset: 'MATIC',
    position_id: 'mock-matic-claim-7',
    claim_status: 'failed',
    outcome: 'lost',
    claimed_amount_usdc: 0,
    retry_count: 5,
    status: 'FAIL',
    retry: 5,
    max_retry: 5,
    next_sec: null,
    payout: null,
  },
];

// ╔══════════════════════════════════════════════════════════════╗
// ║  Search — sinyal araniyor                                    ║
// ╚══════════════════════════════════════════════════════════════╝

/**
 * 2 search tile:
 *  5. BTC search 6/6 HAZIR — tum rules pass, signal_ready true
 *  6. ETH search 4/6 BEKLE — Delta fail + BotMax waiting, signal_ready false
 */

const BTC_RULES_PASS: RuleSpecContract[] = [
  { label: 'Zaman',  live_value: '3:15',   threshold_text: '30-270s', state: 'pass' },
  { label: 'Fiyat',  live_value: '111234', threshold_text: '≥ 80',    state: 'pass' },
  { label: 'Delta',  live_value: '$55',    threshold_text: '≥ $50',   state: 'pass' },
  { label: 'Spread', live_value: '1.8%',   threshold_text: '≤ 3%',    state: 'pass' },
  { label: 'EvMax',  live_value: '0/1',    threshold_text: '1',       state: 'pass' },
  { label: 'BotMax', live_value: '2/3',    threshold_text: '3',       state: 'pass' },
];

const ETH_RULES_MIXED: RuleSpecContract[] = [
  { label: 'Zaman',  live_value: '2:48', threshold_text: '30-270s', state: 'pass' },
  { label: 'Fiyat',  live_value: '3841', threshold_text: '≥ 80',    state: 'pass' },
  { label: 'Delta',  live_value: '$32', threshold_text: '≥ $50',   state: 'fail' },
  { label: 'Spread', live_value: '1.4%', threshold_text: '≤ 3%',    state: 'pass' },
  { label: 'EvMax',  live_value: '0/1',  threshold_text: '1',       state: 'pass' },
  { label: 'BotMax', live_value: '—',    threshold_text: '3',       state: 'waiting' },
];

export const MOCK_SEARCH: SearchTileContract[] = [
  // 5) BTC search ready 6/6
  {
    tile_id: 'mock-search-btc-1',
    coin: 'BTC',
    event_url: 'https://polymarket.com/event/bitcoin-up-or-down-5-min-search',
    pnl_big: '6/6',
    pnl_amount: 'HAZIR',
    pnl_tone: 'profit',
    ptb: '111,234',
    live: '111,289',
    delta: '$55',
    rules: BTC_RULES_PASS,
    activity: {
      text: 'Sinyal hazır — FOK 56 gönderiliyor',
      severity: 'success',
    },
    signal_ready: true,
    type: 'ok',
  },
  // 6) ETH search wait 4/6
  {
    tile_id: 'mock-search-eth-2',
    coin: 'ETH',
    event_url: 'https://polymarket.com/event/ethereum-up-or-down-5-min-search',
    pnl_big: '4/6',
    pnl_amount: 'BEKLE',
    pnl_tone: 'pending',
    ptb: '3,841.23',
    live: '3,839.72',
    delta: '$32',
    rules: ETH_RULES_MIXED,
    activity: {
      text: 'Delta yetersiz — sinyal bekleniyor',
      severity: 'warning',
    },
    signal_ready: false,
    type: 'wait',
  },

  // 7) BNB search — spread fail
  {
    tile_id: 'mock-search-bnb-3',
    coin: 'BNB',
    event_url: 'https://polymarket.com/event/bnb-up-or-down-5-min-search',
    pnl_big: '5/6',
    pnl_amount: 'BLOK',
    pnl_tone: 'loss',
    ptb: '595.32',
    live: '595.18',
    delta: '$0.14',
    rules: [
      { label: 'Zaman',  live_value: '4:18', threshold_text: '30-270s', state: 'pass' },
      { label: 'Fiyat',  live_value: '595',  threshold_text: '≥ 80',    state: 'pass' },
      { label: 'Delta',  live_value: '$78',  threshold_text: '≥ $50',   state: 'pass' },
      { label: 'Spread', live_value: '4.8%', threshold_text: '≤ 3%',    state: 'fail' },
      { label: 'EvMax',  live_value: '0/1',  threshold_text: '1',       state: 'pass' },
      { label: 'BotMax', live_value: '2/3',  threshold_text: '3',       state: 'pass' },
    ],
    activity: {
      text: '✕ Spread çok yüksek — kural blokladı',
      severity: 'error',
    },
    signal_ready: false,
    type: 'wait',
  },

  // 8) AVAX search — zaman bekliyor
  {
    tile_id: 'mock-search-avax-4',
    coin: 'AVAX',
    event_url: 'https://polymarket.com/event/avax-up-or-down-5-min-search',
    pnl_big: '5/6',
    pnl_amount: 'BEKLE',
    pnl_tone: 'pending',
    ptb: '38.42',
    live: '38.51',
    delta: '$0.09',
    rules: [
      { label: 'Zaman',  live_value: '0:18', threshold_text: '30-270s', state: 'fail' },
      { label: 'Fiyat',  live_value: '38',   threshold_text: '≥ 30',    state: 'pass' },
      { label: 'Delta',  live_value: '$72',  threshold_text: '≥ $50',   state: 'pass' },
      { label: 'Spread', live_value: '2.1%', threshold_text: '≤ 3%',    state: 'pass' },
      { label: 'EvMax',  live_value: '0/1',  threshold_text: '1',       state: 'pass' },
      { label: 'BotMax', live_value: '2/3',  threshold_text: '3',       state: 'pass' },
    ],
    activity: {
      text: '⏱ Zaman aralığı dışı — bir sonraki cycle bekleniyor',
      severity: 'info',
    },
    signal_ready: false,
    type: 'wait',
  },
];

// ╔══════════════════════════════════════════════════════════════╗
// ║  Idle — pasif coinler                                        ║
// ╚══════════════════════════════════════════════════════════════╝

/**
 * 2 idle tile:
 *  7. XRP idle manual off — bot_stopped, kullanici manuel kapatti
 *  8. ADA idle no settings — waiting_rules, ayar henuz girilmedi
 */

const ADA_RULES_DISABLED: RuleSpecContract[] = [
  { label: 'Zaman',  live_value: '—', state: 'disabled' },
  { label: 'Fiyat',  live_value: '—', state: 'disabled' },
  { label: 'Spread', live_value: '—', state: 'disabled' },
];

export const MOCK_IDLE: IdleTileContract[] = [
  // 7) XRP idle manual off
  {
    tile_id: 'mock-idle-xrp-1',
    coin: 'XRP',
    idle_kind: 'bot_stopped',
    msg: 'Manuel kapatıldı',
    activity: {
      text: 'Aktif etmek için $ butonuna bas',
      severity: 'info',
    },
    rules: null,
    event_url: 'https://polymarket.com/event/ripple-up-or-down-5-min',
  },
  // 8) ADA idle no settings
  {
    tile_id: 'mock-idle-ada-2',
    coin: 'ADA',
    idle_kind: 'waiting_rules',
    msg: 'Ayar henüz girilmedi',
    activity: {
      text: 'Ayarsız — settings panelinden tanımla',
      severity: 'off',
    },
    rules: ADA_RULES_DISABLED,
    event_url: null,
  },

  // 9) DOGE — cooldown (TP sonrasi)
  {
    tile_id: 'mock-idle-doge-3',
    coin: 'DOGE',
    idle_kind: 'cooldown',
    msg: 'Cooldown · 38s',
    activity: {
      text: '⏱ Yeni pozisyon için 38 saniye cooldown',
      severity: 'pending',
    },
    rules: null,
    event_url: 'https://polymarket.com/event/doge-up-or-down-5-min',
  },

  // 10) Hicbir coin — no_events
  {
    tile_id: 'mock-idle-no-events',
    coin: null,
    idle_kind: 'no_events',
    msg: 'Aktif 5M event yok',
    activity: {
      text: 'Polymarket discovery boş — yeni event bekleniyor',
      severity: 'info',
    },
    rules: null,
    event_url: null,
  },

  // 11) LINK — error (fetch hatasi)
  {
    tile_id: 'mock-idle-link-err',
    coin: 'LINK',
    idle_kind: 'error',
    msg: 'PTB fetch hatası',
    activity: {
      text: '✕ Polymarket fiyat çekilemedi — son deneme: 30s önce',
      severity: 'error',
    },
    rules: null,
    event_url: null,
  },
];

// ╔══════════════════════════════════════════════════════════════╗
// ║  Tek noktadan export                                         ║
// ╚══════════════════════════════════════════════════════════════╝

/**
 * MOCK_DATA — DashboardSidebarPreview composition'unda mockMode iken
 * useDashboardData hook'u yerine bu kullanilir.
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
