/**
 * GlobalSettingsModal — exit policy + system workflow ayarları.
 *
 * 3 grup, 12 alan (11 editable, 1 read-only).
 * Backend tek otorite — frontend karar üretmez.
 * GET ile mevcut değerler dolar, POST partial update gönderir.
 * sl_jump_threshold read-only — backend'e geri yazılmaz.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { COLOR, FONT, SIZE, ensureStyles } from './styles';

ensureStyles('global-settings-modal-v1', `
.gsm-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.65);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
}
.gsm-modal {
  background: ${COLOR.bgRaised};
  border: 1px solid ${COLOR.borderStrong};
  border-radius: ${SIZE.radiusLg}px;
  max-width: 560px;
  width: 100%;
  padding: 24px 28px 20px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.6), 0 0 0 1px ${COLOR.brandSoft};
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 90vh;
  overflow-y: auto;
}
.gsm-title {
  font-size: 17px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
  margin-bottom: 2px;
}
.gsm-group-label {
  font-size: 12px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.cyan};
  letter-spacing: 0.06em;
  text-transform: uppercase;
  margin-top: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid ${COLOR.border};
}
.gsm-field {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 32px;
}
.gsm-field-label {
  font-size: 12px;
  font-weight: ${FONT.weight.semibold};
  color: ${COLOR.textMuted};
  min-width: 200px;
  flex-shrink: 0;
}
.gsm-input {
  width: 100px;
  max-width: 100px;
  padding: 6px 10px;
  border-radius: ${SIZE.radius}px;
  border: 1px solid ${COLOR.border};
  background: ${COLOR.surface};
  color: ${COLOR.text};
  font-family: ${FONT.mono};
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s;
}
.gsm-input:focus { border-color: ${COLOR.cyan}; }
.gsm-input[disabled] { opacity: 0.35; cursor: not-allowed; }
.gsm-unit {
  font-size: 11px;
  color: ${COLOR.textDim};
  min-width: 30px;
}
.gsm-toggle {
  position: relative;
  width: 38px;
  height: 20px;
  border-radius: 10px;
  border: none;
  cursor: pointer;
  transition: background 0.2s;
  flex-shrink: 0;
  padding: 0;
}
.gsm-toggle::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.2s;
}
.gsm-toggle.on { background: ${COLOR.green}; }
.gsm-toggle.on::after { transform: translateX(18px); }
.gsm-toggle.off { background: ${COLOR.border}; }
.gsm-toggle[disabled] { opacity: 0.35; cursor: not-allowed; }
.gsm-readonly {
  font-family: ${FONT.mono};
  font-size: 13px;
  color: ${COLOR.textMuted};
  padding: 6px 10px;
  background: ${COLOR.surface};
  border: 1px dashed ${COLOR.border};
  border-radius: ${SIZE.radius}px;
  opacity: 0.6;
}
.gsm-readonly-note {
  font-size: 10px;
  color: ${COLOR.textDim};
  font-style: italic;
}
.gsm-warn {
  padding: 8px 12px;
  border-radius: ${SIZE.radius}px;
  font-size: 11px;
  line-height: 1.5;
  font-weight: ${FONT.weight.semibold};
}
.gsm-warn.info {
  background: rgba(6,182,212,0.08);
  border: 1px solid rgba(6,182,212,0.25);
  color: ${COLOR.cyan};
}
.gsm-warn.orange {
  background: rgba(234,179,8,0.08);
  border: 1px solid rgba(234,179,8,0.3);
  color: ${COLOR.yellow};
}
.gsm-warn.red {
  background: ${COLOR.redSoft};
  border: 1px solid ${COLOR.red};
  color: ${COLOR.red};
}
.gsm-desc {
  font-size: 10px;
  color: ${COLOR.textDim};
  padding-left: 208px;
  margin-top: -4px;
}
.gsm-status {
  padding: 8px 12px;
  border-radius: ${SIZE.radius}px;
  font-size: 12px;
  font-weight: ${FONT.weight.semibold};
}
.gsm-status.ok { background: ${COLOR.greenSoft}; border: 1px solid ${COLOR.green}; color: ${COLOR.green}; }
.gsm-status.err { background: ${COLOR.redSoft}; border: 1px solid ${COLOR.red}; color: ${COLOR.red}; }
.gsm-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  margin-top: 4px;
}
.gsm-btn {
  padding: 9px 20px;
  border-radius: ${SIZE.radius}px;
  font-size: 13px;
  font-weight: ${FONT.weight.bold};
  font-family: ${FONT.sans};
  cursor: pointer;
  border: 1px solid;
  transition: filter 0.15s, opacity 0.15s;
}
.gsm-btn[disabled] { opacity: 0.4; cursor: not-allowed; }
.gsm-btn.primary { background: ${COLOR.cyan}; border-color: ${COLOR.cyan}; color: ${COLOR.bg}; }
.gsm-btn.primary:not([disabled]):hover { filter: brightness(1.1); }
.gsm-btn.secondary { background: ${COLOR.surface}; border-color: ${COLOR.border}; color: ${COLOR.text}; }
.gsm-btn.secondary:not([disabled]):hover { background: ${COLOR.surfaceHover}; }
`);

// ── Types ──

interface GlobalSettings {
  auto_start_bot_on_startup: boolean;
  bot_max_positions: number;
  block_new_entries_when_claim_pending: boolean;
  tp_percentage: number;
  tp_reevaluate: boolean;
  sl_enabled: boolean;
  sl_percentage: number;
  sl_jump_threshold: number;
  fs_time_enabled: boolean;
  fs_time_seconds: number;
  fs_pnl_enabled: boolean;
  fs_pnl_pct: number;
}

const MOCK_DEFAULTS: GlobalSettings = {
  auto_start_bot_on_startup: false,
  bot_max_positions: 3,
  block_new_entries_when_claim_pending: true,
  tp_percentage: 5.0,
  tp_reevaluate: true,
  sl_enabled: true,
  sl_percentage: 3.0,
  sl_jump_threshold: 0.15,
  fs_time_enabled: true,
  fs_time_seconds: 30,
  fs_pnl_enabled: true,
  fs_pnl_pct: 5.0,
};

// ── Helpers ──

/** Sayı normalizasyonu: virgül → nokta, binlik ayırıcı temizle */
function normalizeNumeric(raw: string): string {
  if (!raw) return raw;
  let s = raw;
  if (/^\d{1,3}(,\d{3})+$/.test(s)) {
    s = s.replace(/,/g, '');
  } else {
    s = s.replace(/,/g, '.');
  }
  const parts = s.split('.');
  if (parts.length > 2) {
    s = parts[0] + '.' + parts.slice(1).join('');
  }
  return s;
}

// ── Component ──

export interface GlobalSettingsModalProps {
  onClose: () => void;
  mockMode?: boolean;
}

export default function GlobalSettingsModal({ onClose, mockMode }: GlobalSettingsModalProps) {
  const [data, setData] = useState<GlobalSettings | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ text: string; ok: boolean } | null>(null);

  // ── Local form state (string for numeric inputs) ──
  const [autoStart, setAutoStart] = useState(false);
  const [botMax, setBotMax] = useState('3');
  const [blockClaim, setBlockClaim] = useState(true);
  const [tpPct, setTpPct] = useState('5');
  const [tpReevaluate, setTpReevaluate] = useState(true);
  const [slEnabled, setSlEnabled] = useState(true);
  const [slPct, setSlPct] = useState('3');
  const [slJumpThreshold, setSlJumpThreshold] = useState(0.15);
  const [fsTimeEnabled, setFsTimeEnabled] = useState(true);
  const [fsTimeSec, setFsTimeSec] = useState('30');
  const [fsPnlEnabled, setFsPnlEnabled] = useState(true);
  const [fsPnlPct, setFsPnlPct] = useState('5');

  // ── Load on mount ──
  const fetchedRef = useRef(false);
  useEffect(() => {
    if (fetchedRef.current) return;
    fetchedRef.current = true;

    if (mockMode) {
      const d = MOCK_DEFAULTS;
      setData(d);
      setAutoStart(d.auto_start_bot_on_startup);
      setBotMax(String(d.bot_max_positions));
      setBlockClaim(d.block_new_entries_when_claim_pending);
      setTpPct(String(d.tp_percentage));
      setTpReevaluate(d.tp_reevaluate);
      setSlEnabled(d.sl_enabled);
      setSlPct(String(d.sl_percentage));
      setSlJumpThreshold(d.sl_jump_threshold);
      setFsTimeEnabled(d.fs_time_enabled);
      setFsTimeSec(String(d.fs_time_seconds));
      setFsPnlEnabled(d.fs_pnl_enabled);
      setFsPnlPct(String(d.fs_pnl_pct));
      setLoaded(true);
      return;
    }

    (async () => {
      try {
        const resp = await fetch('/api/settings/global');
        if (!resp.ok) throw new Error(`${resp.status}`);
        const d: GlobalSettings = await resp.json();
        setData(d);
        setAutoStart(d.auto_start_bot_on_startup);
        setBotMax(String(d.bot_max_positions));
        setBlockClaim(d.block_new_entries_when_claim_pending);
        setTpPct(String(d.tp_percentage));
        setTpReevaluate(d.tp_reevaluate);
        setSlEnabled(d.sl_enabled);
        setSlPct(String(d.sl_percentage));
        setSlJumpThreshold(d.sl_jump_threshold);
        setFsTimeEnabled(d.fs_time_enabled);
        setFsTimeSec(String(d.fs_time_seconds));
        setFsPnlEnabled(d.fs_pnl_enabled);
        setFsPnlPct(String(d.fs_pnl_pct));
        setLoaded(true);
      } catch {
        setLoaded(true);
        setStatusMsg({ text: 'Ayarlar yüklenemedi', ok: false });
      }
    })();
  }, [mockMode]);

  // ── Save ──
  const handleSave = useCallback(async () => {
    if (!data) return;
    setStatusMsg(null);

    // Build partial update — sadece değişen alanlar
    const body: Record<string, unknown> = {};
    if (autoStart !== data.auto_start_bot_on_startup) body.auto_start_bot_on_startup = autoStart;
    const botMaxNum = parseInt(botMax, 10);
    if (!isNaN(botMaxNum) && botMaxNum !== data.bot_max_positions) body.bot_max_positions = botMaxNum;
    if (blockClaim !== data.block_new_entries_when_claim_pending) body.block_new_entries_when_claim_pending = blockClaim;
    const tpNum = parseFloat(tpPct);
    if (!isNaN(tpNum) && tpNum !== data.tp_percentage) body.tp_percentage = tpNum;
    if (tpReevaluate !== data.tp_reevaluate) body.tp_reevaluate = tpReevaluate;
    if (slEnabled !== data.sl_enabled) body.sl_enabled = slEnabled;
    const slNum = parseFloat(slPct);
    if (!isNaN(slNum) && slNum !== data.sl_percentage) body.sl_percentage = slNum;
    if (fsTimeEnabled !== data.fs_time_enabled) body.fs_time_enabled = fsTimeEnabled;
    const fsTimeNum = parseInt(fsTimeSec, 10);
    if (!isNaN(fsTimeNum) && fsTimeNum !== data.fs_time_seconds) body.fs_time_seconds = fsTimeNum;
    if (fsPnlEnabled !== data.fs_pnl_enabled) body.fs_pnl_enabled = fsPnlEnabled;
    const fsPnlNum = parseFloat(fsPnlPct);
    if (!isNaN(fsPnlNum) && fsPnlNum !== data.fs_pnl_pct) body.fs_pnl_pct = fsPnlNum;

    if (Object.keys(body).length === 0) {
      setStatusMsg({ text: 'Değişiklik yok', ok: true });
      return;
    }

    if (mockMode) {
      setStatusMsg({ text: `${Object.keys(body).length} ayar güncellendi`, ok: true });
      // Mock: data'yı güncelle
      setData(prev => prev ? { ...prev, ...body } as GlobalSettings : prev);
      return;
    }

    setSaving(true);
    try {
      const resp = await fetch('/api/settings/global', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error(`${resp.status}`);
      const result = await resp.json();

      let msg = result.message || `${Object.keys(body).length} ayar güncellendi`;
      if (result.has_open_positions) {
        msg += ' — Açık pozisyonlara anında uygulandı';
      }
      setStatusMsg({ text: msg, ok: true });
      // Backend'den dönen sonuçla data'yı güncelle
      setData(prev => prev ? { ...prev, ...body } as GlobalSettings : prev);
    } catch {
      setStatusMsg({ text: 'Güncelleme hatası — tekrar deneyin', ok: false });
    } finally {
      setSaving(false);
    }
  }, [data, autoStart, botMax, blockClaim, tpPct, tpReevaluate, slEnabled, slPct, fsTimeEnabled, fsTimeSec, fsPnlEnabled, fsPnlPct, mockMode]);

  // ── ESC ──
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  if (!loaded) return null;

  // ── Conditional warnings ──
  const slOff = !slEnabled;
  const fsTimeOff = !fsTimeEnabled;
  const fsPnlOff = !fsPnlEnabled;
  const allFsOff = fsTimeOff && fsPnlOff;

  // ── Render helpers ──
  const Toggle = ({ value, onChange, disabled }: { value: boolean; onChange: (v: boolean) => void; disabled?: boolean }) => (
    <button
      type="button"
      className={`gsm-toggle ${value ? 'on' : 'off'}`}
      onClick={() => { if (!disabled) { onChange(!value); setStatusMsg(null); } }}
      disabled={disabled}
      aria-pressed={value}
    />
  );

  const NumInput = ({ value, onChange, disabled, unit }: { value: string; onChange: (v: string) => void; disabled?: boolean; unit?: string }) => (
    <>
      <input
        className="gsm-input"
        type="text"
        inputMode="decimal"
        value={value}
        onChange={e => { onChange(normalizeNumeric(e.target.value)); setStatusMsg(null); }}
        disabled={disabled || saving}
      />
      {unit && <span className="gsm-unit">{unit}</span>}
    </>
  );

  return (
    <div className="gsm-overlay" onClick={onClose} role="presentation">
      <div className="gsm-modal" onClick={e => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Genel Ayarlar">

        <div className="gsm-title">Genel Ayarlar</div>

        {/* ── Kalıcı uyarı ── */}
        <div className="gsm-warn info">
          TP, SL ve Zorla Satış değişiklikleri mevcut açık pozisyonlara anında uygulanır.
        </div>

        {/* ══════ GRUP A: GENEL ══════ */}
        <div className="gsm-group-label">Genel</div>

        <div className="gsm-field">
          <span className="gsm-field-label">Otomatik Başlatma</span>
          <Toggle value={autoStart} onChange={setAutoStart} disabled={saving} />
        </div>
        <div className="gsm-desc">
          Uygulama yeniden başlatıldığında bot otomatik çalışmaya başlar. Credential ve bakiye kontrolü sonrası aktif olur.
        </div>

        <div className="gsm-field">
          <span className="gsm-field-label">Maksimum Açık Pozisyon</span>
          <NumInput value={botMax} onChange={setBotMax} unit="adet" />
        </div>
        <div className="gsm-desc">Min: 1 — Max: 50</div>

        <div className="gsm-field">
          <span className="gsm-field-label">Claim Beklerken Giriş Engelle</span>
          <Toggle value={blockClaim} onChange={setBlockClaim} disabled={saving} />
        </div>

        {/* ══════ GRUP B: TP / SL ══════ */}
        <div className="gsm-group-label">Take Profit / Stop Loss</div>

        <div className="gsm-field">
          <span className="gsm-field-label">Take Profit</span>
          <NumInput value={tpPct} onChange={setTpPct} unit="%" />
        </div>
        <div className="gsm-desc">Min: 0.1 — Max: 100</div>

        <div className="gsm-field">
          <span className="gsm-field-label">TP Yeniden Değerlendir</span>
          <Toggle value={tpReevaluate} onChange={setTpReevaluate} disabled={saving} />
        </div>

        <div className="gsm-field">
          <span className="gsm-field-label">Stop Loss Aktif</span>
          <Toggle value={slEnabled} onChange={setSlEnabled} disabled={saving} />
        </div>

        <div className="gsm-field">
          <span className="gsm-field-label">Stop Loss</span>
          <NumInput value={slPct} onChange={setSlPct} disabled={!slEnabled} unit="%" />
        </div>
        <div className="gsm-desc">Min: 0.1 — Max: 100</div>

        {/* SL kapalı uyarısı */}
        {slOff && (
          <div className="gsm-warn red">
            Stop-Loss kapalı — zarar sınırlaması olmadan işlem açılacak. Pozisyonlar sadece TP veya Zorla Satış ile kapanabilir.
          </div>
        )}

        <div className="gsm-field">
          <span className="gsm-field-label">SL Atlama Eşiği</span>
          <span className="gsm-readonly">%{(slJumpThreshold * 100).toFixed(0)}</span>
          <span className="gsm-readonly-note">salt okunur</span>
        </div>
        <div className="gsm-desc">Ani fiyat sıçramalarında SL tetiklenmesini engeller. Bu değer sistem tarafından yönetilir.</div>

        {/* ══════ GRUP C: ZORLA SATIŞ ══════ */}
        <div className="gsm-group-label">Zorla Satış (Force Sell)</div>

        <div className="gsm-field">
          <span className="gsm-field-label">Süre Bazlı Zorla Satış</span>
          <Toggle value={fsTimeEnabled} onChange={setFsTimeEnabled} disabled={saving} />
        </div>

        <div className="gsm-field">
          <span className="gsm-field-label">Kalan Süre Eşiği</span>
          <NumInput value={fsTimeSec} onChange={setFsTimeSec} disabled={!fsTimeEnabled} unit="saniye" />
        </div>
        <div className="gsm-desc">Min: 1 — Max: 299</div>

        {/* FS Time kapalı uyarısı */}
        {fsTimeOff && !allFsOff && (
          <div className="gsm-warn orange">
            Zorla Satış (Süre) kapalı — pozisyonlar süre dolduğunda otomatik kapanmayacak.
          </div>
        )}

        <div className="gsm-field">
          <span className="gsm-field-label">Zarar Bazlı Zorla Satış</span>
          <Toggle value={fsPnlEnabled} onChange={setFsPnlEnabled} disabled={saving} />
        </div>

        <div className="gsm-field">
          <span className="gsm-field-label">Zarar Eşiği</span>
          <NumInput value={fsPnlPct} onChange={setFsPnlPct} disabled={!fsPnlEnabled} unit="%" />
        </div>
        <div className="gsm-desc">Min: 0.1 — Max: 100</div>

        {/* Tüm FS kapalı uyarısı */}
        {allFsOff && (
          <div className="gsm-warn red">
            Tüm Zorla Satış kuralları kapalı — pozisyonlar sadece TP veya SL ile kapanabilir. Süre bittiğinde açık kalan pozisyonlar settlement'a bırakılır.
          </div>
        )}

        {/* ── Status ── */}
        {statusMsg && (
          <div className={`gsm-status ${statusMsg.ok ? 'ok' : 'err'}`}>
            {statusMsg.text}
          </div>
        )}

        {/* ── Actions ── */}
        <div className="gsm-actions">
          <button type="button" className="gsm-btn secondary" onClick={onClose} disabled={saving}>
            Kapat
          </button>
          <button type="button" className="gsm-btn primary" onClick={handleSave} disabled={saving}>
            {saving ? 'Kaydediliyor...' : 'Güncelle'}
          </button>
        </div>

      </div>
    </div>
  );
}
