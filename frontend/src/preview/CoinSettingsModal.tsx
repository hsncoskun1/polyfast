/**
 * CoinSettingsModal — per-coin entry rule ayarları.
 *
 * 8 editable alan + 1 locked spread bilgi satırı.
 * Governance backend'den gelir — frontend kendi kararını üretmez.
 * Save sonrası: configured + missing_fields backend'den döner.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { COLOR, FONT, SIZE, ensureStyles } from './styles';
import type { FieldPolicy, CoinSettingsReadResponse } from '../api/coin';

ensureStyles('coin-settings-modal-v1', `
.csm-modal {
  background: ${COLOR.bgRaised};
  border: 1px solid ${COLOR.borderStrong};
  border-radius: ${SIZE.radiusLg}px;
  max-width: 480px;
  width: 100%;
  padding: 24px 24px 20px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.6), 0 0 0 1px ${COLOR.brandSoft};
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-height: 90vh;
  overflow-y: auto;
}
.csm-title {
  font-size: 17px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
}
.csm-group-label {
  font-size: 11px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.cyan};
  letter-spacing: 0.06em;
  text-transform: uppercase;
  margin-top: 4px;
}
.csm-field {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.csm-field-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.csm-field-label {
  font-size: 12px;
  font-weight: ${FONT.weight.semibold};
  color: ${COLOR.textMuted};
  min-width: 100px;
}
.csm-input {
  flex: 1;
  padding: 7px 10px;
  border-radius: ${SIZE.radius}px;
  border: 1px solid ${COLOR.border};
  background: ${COLOR.surface};
  color: ${COLOR.text};
  font-family: ${FONT.mono};
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s;
}
.csm-input:focus { border-color: ${COLOR.cyan}; }
.csm-input.error { border-color: ${COLOR.red}; box-shadow: 0 0 0 2px rgba(239,68,68,0.15); }
.csm-input[disabled] { opacity: 0.4; cursor: not-allowed; }
.csm-select {
  flex: 1;
  padding: 7px 10px;
  border-radius: ${SIZE.radius}px;
  border: 1px solid ${COLOR.border};
  background: ${COLOR.surface};
  color: ${COLOR.text};
  font-family: ${FONT.sans};
  font-size: 13px;
  outline: none;
}
.csm-unit {
  font-size: 11px;
  color: ${COLOR.textDim};
  min-width: 40px;
}
.csm-hint {
  font-size: 10px;
  color: ${COLOR.textDim};
  padding-left: 108px;
}
.csm-locked {
  padding: 10px 14px;
  border-radius: ${SIZE.radius}px;
  border: 1px dashed ${COLOR.border};
  background: ${COLOR.surface};
  opacity: 0.5;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.csm-locked-title {
  font-size: 12px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.textMuted};
}
.csm-locked-desc {
  font-size: 11px;
  color: ${COLOR.textDim};
  line-height: 1.4;
}
.csm-status {
  padding: 8px 12px;
  border-radius: ${SIZE.radius}px;
  font-size: 12px;
  font-weight: ${FONT.weight.semibold};
}
.csm-status.ok { background: ${COLOR.greenSoft}; border: 1px solid ${COLOR.green}; color: ${COLOR.green}; }
.csm-status.warn { background: ${COLOR.redSoft}; border: 1px solid ${COLOR.red}; color: ${COLOR.red}; }
.csm-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}
.csm-btn {
  padding: 9px 20px;
  border-radius: ${SIZE.radius}px;
  font-size: 13px;
  font-weight: ${FONT.weight.bold};
  font-family: ${FONT.sans};
  cursor: pointer;
  border: 1px solid;
  transition: filter 0.15s, opacity 0.15s;
}
.csm-btn[disabled] { opacity: 0.4; cursor: not-allowed; }
.csm-btn.primary { background: ${COLOR.cyan}; border-color: ${COLOR.cyan}; color: ${COLOR.bg}; }
.csm-btn.primary:not([disabled]):hover { filter: brightness(1.1); }
.csm-btn.secondary { background: ${COLOR.surface}; border-color: ${COLOR.border}; color: ${COLOR.text}; }
.csm-btn.secondary:not([disabled]):hover { background: ${COLOR.surfaceHover}; }
`);

// ── Field definitions ──

interface FieldDef {
  key: string;
  label: string;
  unit: string;
  type: 'number' | 'select';
  options?: { value: string; label: string }[];
  hint?: string;
}

const SIDE_OPTIONS = [
  { value: 'dominant_only', label: 'Dominant (max taraf)' },
  { value: 'up_only', label: 'Sadece UP' },
  { value: 'down_only', label: 'Sadece DOWN' },
];

const FIELDS: FieldDef[] = [
  { key: 'side_mode', label: 'Trade Yönü', unit: '', type: 'select', options: SIDE_OPTIONS },
  { key: 'delta_threshold', label: 'Delta Eşiği', unit: 'USD', type: 'number', hint: 'PTB ile coin fiyatı arasındaki fark' },
  { key: 'price_min', label: 'Min Fiyat', unit: '(0-100)', type: 'number' },
  { key: 'price_max', label: 'Max Fiyat', unit: '(0-100)', type: 'number' },
  { key: 'time_min', label: 'Min Süre', unit: 'saniye', type: 'number', hint: 'Event bitimine kalan min süre' },
  { key: 'time_max', label: 'Max Süre', unit: 'saniye', type: 'number', hint: 'Event bitimine kalan max süre' },
  { key: 'event_max', label: 'Event Max', unit: 'fill', type: 'number', hint: 'Tek event\'te max alış sayısı' },
  { key: 'order_amount', label: 'İşlem Tutarı', unit: 'USD', type: 'number' },
];

// ── Component ──

export interface CoinSettingsModalProps {
  symbol: string;
  onClose: () => void;
  mockMode?: boolean;
}

export default function CoinSettingsModal({ symbol, onClose, mockMode }: CoinSettingsModalProps) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [governance, setGovernance] = useState<Record<string, FieldPolicy>>({});
  const [errorFields, setErrorFields] = useState<Set<string>>(new Set());
  const [statusMsg, setStatusMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);

  // Fetch settings on mount
  const fetchedRef = useRef(false);
  useEffect(() => {
    if (fetchedRef.current) return;
    fetchedRef.current = true;

    if (mockMode) {
      // Mock defaults
      const mockVals: Record<string, string> = {};
      FIELDS.forEach(f => { mockVals[f.key] = f.key === 'side_mode' ? 'dominant_only' : ''; });
      setValues(mockVals);
      setGovernance({
        side_mode: { visible: true, editable: true, locked: false },
        delta_threshold: { visible: true, editable: true, locked: false },
        price_min: { visible: true, editable: true, locked: false },
        price_max: { visible: true, editable: true, locked: false },
        time_min: { visible: true, editable: true, locked: false },
        time_max: { visible: true, editable: true, locked: false },
        event_max: { visible: true, editable: true, locked: false },
        order_amount: { visible: true, editable: true, locked: false },
        spread_max: { visible: true, editable: false, locked: true },
      });
      setLoaded(true);
      return;
    }

    (async () => {
      try {
        const { coinSettingsGet } = await import('../api/coin');
        const data = await coinSettingsGet(symbol);
        const vals: Record<string, string> = {};
        for (const f of FIELDS) {
          const raw = data.settings[f.key];
          vals[f.key] = raw != null ? String(raw) : '';
        }
        setValues(vals);
        setGovernance(data.field_governance as Record<string, FieldPolicy>);

        if (data.missing_fields.length > 0) {
          setStatusMsg({ text: `${data.missing_fields.length} eksik alan`, ok: false });
        } else if (data.configured) {
          setStatusMsg({ text: 'Ayarlar tamam', ok: true });
        }
        setLoaded(true);
      } catch {
        setLoaded(true);
      }
    })();
  }, [symbol, mockMode]);

  // Side mode'a göre price hint
  const sideMode = values.side_mode || 'dominant_only';
  const priceRange = sideMode === 'dominant_only' ? '51-99' : '1-99';

  const handleChange = useCallback((key: string, value: string) => {
    setValues(prev => ({ ...prev, [key]: value }));
    setErrorFields(prev => { const n = new Set(prev); n.delete(key); return n; });
    setStatusMsg(null);
  }, []);

  const handleSave = useCallback(async () => {
    if (mockMode) {
      // Mock: basit boşluk kontrolü
      const missing: string[] = [];
      FIELDS.forEach(f => {
        if (f.key === 'side_mode') return;
        const g = governance[f.key];
        if (g && g.locked) return;
        if (!values[f.key] || values[f.key] === '0') missing.push(f.key);
      });
      if (missing.length > 0) {
        setErrorFields(new Set(missing));
        setStatusMsg({ text: `${missing.length} eksik alan`, ok: false });
      } else {
        setStatusMsg({ text: 'Ayarlar tamamlandı', ok: true });
        setTimeout(() => onClose(), 1000);
      }
      return;
    }

    setSaving(true);
    setErrorFields(new Set());
    setStatusMsg(null);

    try {
      // Sadece editable ve değişmiş alanları gönder
      const body: Record<string, unknown> = {};
      for (const f of FIELDS) {
        const g = governance[f.key];
        if (g && (g.locked || !g.editable)) continue;
        const val = values[f.key];
        if (val === '' || val == null) continue;
        if (f.type === 'select') {
          body[f.key] = val;
        } else {
          body[f.key] = parseFloat(val);
        }
      }

      const { coinSettingsSave } = await import('../api/coin');
      const result = await coinSettingsSave(symbol, body);

      if (result.configured) {
        setStatusMsg({ text: 'Ayarlar tamamlandı', ok: true });
        setTimeout(() => onClose(), 1000);
      } else {
        setErrorFields(new Set(result.missing_fields));
        setStatusMsg({ text: `${result.missing_fields.length} eksik alan`, ok: false });
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Kaydetme hatası';
      // Backend 422 mesajlarını göster
      if (msg.includes('422')) {
        const detail = msg.split('422 ')[1] || 'Geçersiz değer';
        setStatusMsg({ text: detail, ok: false });
      } else {
        setStatusMsg({ text: 'Bağlantı hatası — tekrar deneyin', ok: false });
      }
    } finally {
      setSaving(false);
    }
  }, [mockMode, values, governance, symbol, onClose]);

  // ESC
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  if (!loaded) return null;

  const renderField = (f: FieldDef) => {
    const g = governance[f.key];
    if (g && !g.visible) return null;

    const hasError = errorFields.has(f.key);
    const disabled = saving || (g && (!g.editable || g.locked));

    // Side mode'a göre price hint değiştir
    let hint = f.hint || '';
    if (f.key === 'price_min' || f.key === 'price_max') {
      hint = `Geçerli aralık: ${priceRange}`;
    }

    return (
      <div className="csm-field" key={f.key}>
        <div className="csm-field-row">
          <span className="csm-field-label">{f.label}</span>
          {f.type === 'select' ? (
            <select
              className="csm-select"
              value={values[f.key] || ''}
              onChange={e => handleChange(f.key, e.target.value)}
              disabled={!!disabled}
            >
              {f.options?.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          ) : (
            <input
              type="number"
              className={`csm-input${hasError ? ' error' : ''}`}
              value={values[f.key] || ''}
              onChange={e => handleChange(f.key, e.target.value)}
              disabled={!!disabled}
              step={f.key === 'delta_threshold' || f.key === 'order_amount' ? '0.01' : '1'}
              min="0"
            />
          )}
          {f.unit && <span className="csm-unit">{f.unit}</span>}
        </div>
        {hint && <span className="csm-hint">{hint}</span>}
      </div>
    );
  };

  // Spread locked bilgi satırı
  const spreadGov = governance.spread_max;
  const showSpreadLocked = spreadGov && spreadGov.visible && spreadGov.locked;

  return (
    <div className="dsp-modal-overlay" role="presentation" onClick={onClose}>
      <div className="csm-modal" role="dialog" aria-modal="true" onClick={e => e.stopPropagation()}>
        <div className="csm-title">{symbol} Ayarları</div>

        <div className="csm-group-label">📊 Trade Yönü</div>
        {renderField(FIELDS[0])}

        <div className="csm-group-label">📈 Entry Kuralları</div>
        {FIELDS.slice(1, 7).map(renderField)}

        <div className="csm-group-label">💰 İşlem Tutarı</div>
        {renderField(FIELDS[7])}

        {showSpreadLocked && (
          <div className="csm-locked">
            <div className="csm-locked-title">🔒 Spread — KAPALI</div>
            <div className="csm-locked-desc">
              Bu kural bu sürümde sistem tarafından yönetilmektedir.
              İleri sürümlerde gelişmiş ayarlardan yapılandırılabilir.
            </div>
          </div>
        )}

        {statusMsg && (
          <div className={`csm-status ${statusMsg.ok ? 'ok' : 'warn'}`}>
            {statusMsg.ok ? '✅' : '⚠'} {statusMsg.text}
          </div>
        )}

        <div className="csm-actions">
          <button type="button" className="csm-btn secondary" onClick={onClose} disabled={saving}>
            İptal
          </button>
          <button type="button" className="csm-btn primary" onClick={handleSave} disabled={saving}>
            {saving ? 'Kaydediliyor...' : 'Kaydet'}
          </button>
        </div>
      </div>
    </div>
  );
}
