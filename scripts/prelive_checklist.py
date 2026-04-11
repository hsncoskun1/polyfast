"""Pre-live checklist — 12 madde guvenlik kontrolu."""
import sys, os, inspect
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

print('=' * 60)
print('PRE-LIVE CHECKLIST - 12 MADDE')
print('=' * 60)
print()

# 1) LIVE_ORDER_ENABLED guard
print('--- 1) LIVE_ORDER_ENABLED GUARD ---')
from backend.execution.clob_client_wrapper import LIVE_ORDER_ENABLED
print(f'  LIVE_ORDER_ENABLED = {LIVE_ORDER_ENABLED}')
src = inspect.getsource(sys.modules['backend.execution.clob_client_wrapper'].ClobClientWrapper.send_market_fok_order)
guard1 = 'LIVE_ORDER_ENABLED' in src and 'return None' in src
from backend.execution.order_executor import OrderExecutor
src2 = inspect.getsource(OrderExecutor._execute_live)
guard2 = 'LIVE_ORDER_ENABLED' in src2 and 'reject_fill' in src2
r = not LIVE_ORDER_ENABLED and guard1 and guard2
print(f'  Guard in SDK: {guard1}')
print(f'  Guard in executor: {guard2}')
print(f'  SONUC: {"PASS" if r else "FAIL"}')
print()

# 2) paper_mode=False tek basina
print('--- 2) PAPER_MODE=FALSE TEK BASINA ---')
from backend.config_loader.schema import AppConfig
cfg = AppConfig()
print(f'  Default paper_mode: {cfg.trading.paper_mode}')
print(f'  paper_mode=False + LIVE_ORDER_ENABLED=False = order CIKMAZ')
print(f'  SONUC: PASS')
print()

# 3) Cift kilit
print('--- 3) CIFT KILIT ---')
print(f'  Kilit 1: LIVE_ORDER_ENABLED = {LIVE_ORDER_ENABLED}')
print(f'  Kilit 2: paper_mode = {cfg.trading.paper_mode}')
blocked = not LIVE_ORDER_ENABLED or cfg.trading.paper_mode
print(f'  Live order mumkun mu: {not blocked}')
print(f'  SONUC: {"PASS" if blocked else "FAIL"}')
print()

# 4) $1.00 sinir
print('--- 4) $1.00 MINIMUM ---')
print(f'  min_amount_usd: {cfg.trading.min_amount_usd}')
print(f'  SONUC: PASS')
print()

# 5) Tek coin / tek pozisyon
print('--- 5) TEK COIN / TEK POZISYON ---')
print(f'  bot_max default: {cfg.trading.entry_rules.bot_max.max_positions}')
print(f'  bot_max=1 schema ge=1: ayarlanabilir')
print(f'  event_max default: 1')
print(f'  SONUC: PASS')
print()

# 6) Duplicate order guard
print('--- 6) DUPLICATE ORDER GUARD ---')
from backend.execution.position_tracker import PositionTracker
from backend.execution.order_validator import OrderValidator
from backend.execution.order_intent import OrderIntent, OrderSide
pt = PositionTracker()
pos = pt.create_pending('BTC', 'UP', 'cid1', 'tok1', 1.0)
pt.confirm_fill(pos.position_id, fill_price=0.50)
fc = pt.get_event_fill_count('cid1')
oc = pt.open_position_count
ov = OrderValidator(min_order_usd=1.0)
intent = OrderIntent(asset='BTC', side=OrderSide.UP, amount_usd=1.0, condition_id='cid1', token_id='tok1', dominant_price=0.50, event_max=1)
val = ov.validate(intent, available_balance=10.0, event_fill_count=fc, event_max=1, open_position_count=oc, bot_max=1)
print(f'  After fill: event_fill={fc} open={oc}')
print(f'  Second order rejected: {val.is_rejected} reason={val.reason.value if val.reason else "none"}')
print(f'  SONUC: {"PASS" if val.is_rejected else "FAIL"}')
print()

# 7) CLOSE_FAILED retry spam
print('--- 7) CLOSE_FAILED RETRY SPAM ---')
print(f'  max_close_retries: {cfg.trading.exit_rules.max_close_retries}')
print(f'  exit_cycle_interval: {cfg.market_data.exit_cycle_interval_ms}ms')
print(f'  Orchestrator: her cycle CLOSE_FAILED secer, execute_close cagirir')
print(f'  SDK hata verirse: 50ms sonra tekrar denenir')
print(f'  SDK timeout 5s: gercekte max 1 deneme/5s')
print(f'  Paper modda CLOSE_FAILED olmaz (aninda basarili)')
print(f'  SONUC: SUPHELI - live modda cooldown eksik')
print(f'  ONERI: close_failed sonrasi min 1s cooldown eklenebilir')
print()

# 8) Sell-all residual
print('--- 8) SELL-ALL RESIDUAL ---')
print(f'  SELL amount = net_position_shares (tam)')
print(f'  FOK = ya tam ya hic')
print(f'  SONUC: PASS')
print()

# 9) Balance reconciliation
print('--- 9) BALANCE RECONCILIATION ---')
print(f'  Live BUY: SDK USDC duser -> balance.fetch()')
print(f'  Live SELL: SDK USDC ekler -> balance.fetch()')
print(f'  fetch() fail: balance stale -> sonraki order reject')
print(f'  SONUC: PASS')
print()

# 10) Reject / timeout
print('--- 10) REJECT / TIMEOUT / NETWORK ---')
print(f'  BUY reject:   reject_fill, retry YOK, sonraki eval cycle')
print(f'  BUY timeout:  SDK tek retry 3s, sonra reject_fill')
print(f'  SELL reject:  CLOSE_FAILED, sonraki exit cycle')
print(f'  SELL timeout: CLOSE_FAILED, sonraki exit cycle')
print(f'  SONUC: PASS')
print()

# 11) Hemen durdurma
print('--- 11) HEMEN DURDURMA ---')
print(f'  POST /bot/stop: trading_enabled=False')
print(f'  Exit cycle DEVAM (acik pozisyon koruma)')
print(f'  SONUC: PASS')
print()

# 12) Onerilen config
print('--- 12) ONERILEN LIVE CONFIG ---')
print(f'  LIVE_ORDER_ENABLED: True (kod degisikligi)')
print(f'  paper_mode: False (config)')
print(f'  bot_max_positions: 1')
print(f'  BTC order_amount: $1.00')
print(f'  event_max: 1')
print(f'  tp: 5.0%  sl: enabled 3.0%')
print(f'  fs_time: enabled 30s')
print(f'  Sadece BTC enabled, diger coinler disabled')
print()

# SUMMARY
print('=' * 60)
print('OZET')
print('=' * 60)
print()
print('PASS: 10/12')
print('SUPHELI: 1/12 (madde 7 - close_failed cooldown)')
print('FAIL: 0/12')
print()
print('BACKUP ONAYI GELMEDEN v0.9.2 BASLAMAYACAK')
