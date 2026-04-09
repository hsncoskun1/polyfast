/**
 * CredentialModal — credential giriş/güncelleme modal.
 *
 * Akış: status check → form → save → validate → sonuç
 * Güvenlik: plaintext credential frontend'e dönmez, maskeli placeholder
 * Ürün dili: "kontrol edildi" (doğrulandı DEĞİL)
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { COLOR, FONT, SIZE, ensureStyles } from './styles';
import type {
  CredentialValidateResponse,
  CheckResult,
} from '../api/credential';

// ╔══════════════════════════════════════════════════════════════╗
// ║  CSS                                                         ║
// ╚══════════════════════════════════════════════════════════════╝

ensureStyles('credential-modal-v1', `
.cred-modal {
  background: ${COLOR.bgRaised};
  border: 1px solid ${COLOR.borderStrong};
  border-radius: ${SIZE.radiusLg}px;
  max-width: 520px;
  width: 100%;
  padding: 28px 28px 24px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.6), 0 0 0 1px ${COLOR.brandSoft};
  display: flex;
  flex-direction: column;
  gap: 18px;
  max-height: 90vh;
  overflow-y: auto;
}
.cred-modal-title {
  font-size: 18px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
  letter-spacing: 0.02em;
}
.cred-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cred-group-label {
  font-size: 12px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.cyan};
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.cred-field {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.cred-field-label {
  font-size: 11px;
  font-weight: ${FONT.weight.semibold};
  color: ${COLOR.textMuted};
}
.cred-field-hint {
  font-size: 10px;
  color: ${COLOR.textDim};
}
.cred-input {
  padding: 9px 12px;
  border-radius: ${SIZE.radius}px;
  border: 1px solid ${COLOR.border};
  background: ${COLOR.surface};
  color: ${COLOR.text};
  font-family: ${FONT.mono};
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s;
}
.cred-input:focus {
  border-color: ${COLOR.cyan};
}
.cred-input.error {
  border-color: ${COLOR.red};
  box-shadow: 0 0 0 2px rgba(239,68,68,0.15);
}
.cred-input::placeholder {
  color: ${COLOR.textDim};
  font-style: italic;
}
.cred-input[disabled] {
  opacity: 0.5;
  cursor: not-allowed;
}
.cred-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  margin-top: 4px;
}
.cred-btn {
  padding: 10px 22px;
  border-radius: ${SIZE.radius}px;
  font-size: 13px;
  font-weight: ${FONT.weight.bold};
  font-family: ${FONT.sans};
  cursor: pointer;
  border: 1px solid;
  transition: filter 0.15s, opacity 0.15s;
}
.cred-btn[disabled] { opacity: 0.4; cursor: not-allowed; }
.cred-btn.primary {
  background: ${COLOR.cyan};
  border-color: ${COLOR.cyan};
  color: ${COLOR.bg};
}
.cred-btn.primary:not([disabled]):hover { filter: brightness(1.1); }
.cred-btn.secondary {
  background: ${COLOR.surface};
  border-color: ${COLOR.border};
  color: ${COLOR.text};
}
.cred-btn.secondary:not([disabled]):hover { background: ${COLOR.surfaceHover}; }
.cred-spinner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border-radius: ${SIZE.radius}px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.border};
  font-size: 13px;
  color: ${COLOR.textMuted};
}
.cred-spinner-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: ${COLOR.cyan};
  animation: cred-pulse 1.2s ease-in-out infinite;
}
@keyframes cred-pulse {
  0%,100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.3; transform: scale(0.7); }
}
.cred-checks {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
  border-radius: ${SIZE.radius}px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.border};
}
.cred-check-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.cred-check-icon { font-size: 14px; flex-shrink: 0; }
.cred-check-label { font-weight: ${FONT.weight.semibold}; }
.cred-check-msg { color: ${COLOR.textMuted}; font-size: 12px; }
.cred-result-msg {
  padding: 10px 14px;
  border-radius: ${SIZE.radius}px;
  font-size: 13px;
  font-weight: ${FONT.weight.semibold};
}
.cred-result-msg.success {
  background: ${COLOR.greenSoft};
  border: 1px solid ${COLOR.green};
  color: ${COLOR.green};
}
.cred-result-msg.warning {
  background: ${COLOR.yellowSoft};
  border: 1px solid ${COLOR.yellow};
  color: ${COLOR.yellow};
}
.cred-result-msg.error {
  background: ${COLOR.redSoft};
  border: 1px solid ${COLOR.red};
  color: ${COLOR.red};
}
`);

// ╔══════════════════════════════════════════════════════════════╗
// ║  Types                                                       ║
// ╚══════════════════════════════════════════════════════════════╝

type FieldKey = 'api_key' | 'api_secret' | 'api_passphrase' | 'private_key' | 'funder_address' | 'relayer_key';

interface FieldDef {
  key: FieldKey;
  label: string;
  hint: string;
  group: 'trading' | 'signing' | 'relayer';
}

const FIELDS: FieldDef[] = [
  { key: 'api_key', label: 'API Key', hint: 'Polymarket hesabınızdan alınan CLOB API anahtarı', group: 'trading' },
  { key: 'api_secret', label: 'API Secret', hint: 'API anahtarınıza ait gizli anahtar', group: 'trading' },
  { key: 'api_passphrase', label: 'Passphrase', hint: 'API erişim parolası', group: 'trading' },
  { key: 'private_key', label: 'Private Key', hint: 'Ethereum cüzdan özel anahtarı (64 hex karakter, 0x opsiyonel)', group: 'signing' },
  { key: 'funder_address', label: 'Cüzdan Adresi', hint: 'İşlem yapan Ethereum cüzdan adresi (0x ile başlar)', group: 'signing' },
  { key: 'relayer_key', label: 'Relayer Key', hint: 'Otomatik tahsilat için relayer API anahtarı', group: 'relayer' },
];

const GROUP_LABELS: Record<string, string> = {
  trading: '📡 Trading API',
  signing: '🔐 Signing',
  relayer: '🔄 Relayer',
};

type Phase = 'form' | 'saving' | 'validating' | 'result';

// ╔══════════════════════════════════════════════════════════════╗
// ║  Component                                                   ║
// ╚══════════════════════════════════════════════════════════════╝

export interface CredentialModalProps {
  /** Kapatılabilir mi (has_any=true && is_fully_ready=false) */
  closable: boolean;
  onClose: () => void;
  /** Mock mode — backend fetch skip */
  mockMode?: boolean;
}

export default function CredentialModal({ closable, onClose, mockMode }: CredentialModalProps) {
  // Field state: value (kullanıcı girişi), touched (dokunuldu mu)
  const [values, setValues] = useState<Record<FieldKey, string>>({
    api_key: '', api_secret: '', api_passphrase: '',
    private_key: '', funder_address: '', relayer_key: '',
  });
  const [touched, setTouched] = useState<Record<FieldKey, boolean>>({
    api_key: false, api_secret: false, api_passphrase: false,
    private_key: false, funder_address: false, relayer_key: false,
  });
  const [masked, setMasked] = useState<Record<string, string>>({});
  const [hasAny, setHasAny] = useState(false);
  const [phase, setPhase] = useState<Phase>('form');
  const [errorFields, setErrorFields] = useState<Set<string>>(new Set());
  const [validateResult, setValidateResult] = useState<CredentialValidateResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Fetch status on mount
  const fetchedRef = useRef(false);
  useEffect(() => {
    if (fetchedRef.current || mockMode) return;
    fetchedRef.current = true;
    (async () => {
      try {
        const { credentialStatus } = await import('../api/credential');
        const status = await credentialStatus();
        setHasAny(status.has_any);
        setMasked(status.masked_fields);
      } catch {
        // Status fetch başarısız — form yine de açılır
      }
    })();
  }, [mockMode]);

  // ESC handler (sadece closable ise)
  useEffect(() => {
    if (!closable) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [closable, onClose]);

  const handleChange = useCallback((key: FieldKey, value: string) => {
    setValues(prev => ({ ...prev, [key]: value }));
    setTouched(prev => ({ ...prev, [key]: true }));
    setErrorFields(prev => { const n = new Set(prev); n.delete(key); return n; });
    setErrorMsg(null);
  }, []);

  // Blur'da boş alan kontrolü — anlık kırmızı border
  const handleBlur = useCallback((key: FieldKey) => {
    if (touched[key] && !values[key].trim()) {
      setErrorFields(prev => new Set(prev).add(key));
    }
  }, [touched, values]);

  const handleSave = useCallback(async () => {
    if (mockMode) {
      // Mock'ta da boş alan kontrolü — rasgele değerle onay vermemeli
      const mockMissing = FIELDS.filter(f => !values[f.key].trim()).map(f => f.key);
      if (mockMissing.length > 0) {
        setErrorFields(new Set(mockMissing));
        setErrorMsg(`Eksik alanlar: ${mockMissing.join(', ')}`);
        setPhase('form');
        return;
      }
      // Tüm alanlar dolu — mock validate
      const checks = FIELDS.map(f => {
        // Signing format check (0x prefix)
        if (f.key === 'private_key' || f.key === 'funder_address') {
          const v = values[f.key];
          const hexPart = v.startsWith('0x') ? v.slice(2) : v;
          const validHex = /^[0-9a-fA-F]+$/.test(hexPart);
          if (!validHex) return { name: f.key, label: f.label, status: 'failed' as const, message: 'Geçersiz hex formatı', related_fields: [f.key] };
          if (f.key === 'private_key' && hexPart.length !== 64) return { name: f.key, label: f.label, status: 'failed' as const, message: '64 hex karakter olmalı', related_fields: [f.key] };
          if (f.key === 'funder_address' && !v.startsWith('0x')) return { name: f.key, label: f.label, status: 'failed' as const, message: '0x ile başlamalı', related_fields: [f.key] };
          if (f.key === 'funder_address' && v.length !== 42) return { name: f.key, label: f.label, status: 'failed' as const, message: '42 karakter olmalı', related_fields: [f.key] };
        }
        return { name: f.key, label: f.label, status: 'passed' as const, message: 'Mock OK', related_fields: [f.key] };
      });
      const failedChecks = checks.filter(c => c.status === 'failed');
      const allPassed = failedChecks.length === 0;
      if (failedChecks.length > 0) {
        const failFields = new Set<string>();
        failedChecks.forEach(c => c.related_fields.forEach(rf => failFields.add(rf)));
        setErrorFields(failFields);
      }
      setPhase('result');
      setValidateResult({
        validated: true,
        validation_status: allPassed ? 'passed' : 'partial',
        checks,
        failed_checks: failedChecks.map(c => c.name),
        has_trading_api: true, has_signing: allPassed, has_relayer: true,
        can_place_orders: allPassed, can_auto_claim: allPassed,
        is_fully_ready: allPassed,
        message: allPassed ? 'Mock: Kontrol tamamlandı' : `Mock: ${failedChecks.length} sorunlu alan`,
      });
      return;
    }

    setPhase('saving');
    setErrorMsg(null);
    setErrorFields(new Set());

    try {
      // Sadece dokunulan alanları gönder (partial update)
      const body: Record<string, string> = {};
      for (const f of FIELDS) {
        if (touched[f.key]) {
          body[f.key] = values[f.key];
        }
      }

      // İlk kayıt (has_any=false) → tüm alanlar gönderilmeli
      if (!hasAny) {
        for (const f of FIELDS) {
          body[f.key] = values[f.key];
        }
      }

      const { credentialUpdate } = await import('../api/credential');
      const result = await credentialUpdate(body);

      if (result.missing_fields.length > 0) {
        setErrorFields(new Set(result.missing_fields));
        setErrorMsg(`Eksik alanlar: ${result.missing_fields.join(', ')}`);
        setPhase('form');
        return;
      }

      // Missing yok → otomatik validate
      setPhase('validating');
      const { credentialValidate } = await import('../api/credential');
      const vResult = await credentialValidate();
      setValidateResult(vResult);

      // Failed field vurgulama
      if (vResult.failed_checks.length > 0) {
        const failedFields = new Set<string>();
        for (const c of vResult.checks) {
          if (c.status === 'failed') {
            for (const rf of c.related_fields) failedFields.add(rf);
          }
        }
        setErrorFields(failedFields);
      }

      setPhase('result');
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('Credential save/validate failed:', err);
      setErrorMsg('Bağlantı hatası — tekrar deneyin');
      setPhase('form');
    }
  }, [mockMode, touched, values, hasAny]);

  const handleRetry = useCallback(() => {
    setPhase('form');
    setValidateResult(null);
    setErrorMsg(null);
  }, []);

  const isFormDisabled = phase === 'saving' || phase === 'validating';
  const buttonLabel = hasAny ? 'Güncelle' : 'Kaydet';

  // ── Render ──

  const renderField = (f: FieldDef) => {
    const maskedVal = masked[f.key] || '';
    const placeholder = maskedVal || `${f.label} girin`;
    const hasError = errorFields.has(f.key);
    return (
      <div className="cred-field" key={f.key}>
        <label className="cred-field-label">{f.label}</label>
        <input
          type="password"
          className={`cred-input${hasError ? ' error' : ''}`}
          placeholder={placeholder}
          value={values[f.key]}
          onChange={e => handleChange(f.key, e.target.value)}
          onBlur={() => handleBlur(f.key)}
          disabled={isFormDisabled}
          autoComplete="off"
        />
        <span className="cred-field-hint">{f.hint}</span>
      </div>
    );
  };

  const renderChecks = (checks: CheckResult[]) => (
    <div className="cred-checks">
      {checks.map(c => (
        <div className="cred-check-row" key={c.name}>
          <span className="cred-check-icon">
            {c.status === 'passed' ? '✅' : c.status === 'failed' ? '❌' : '⏭'}
          </span>
          <span className="cred-check-label">{c.label}</span>
          <span className="cred-check-msg">— {c.message}</span>
        </div>
      ))}
    </div>
  );

  // Başarılıysa otomatik kapat (1.5s sonra), başarısızsa otomatik form'a dön (2s sonra)
  useEffect(() => {
    if (phase !== 'result' || !validateResult) return;
    if (validateResult.is_fully_ready) {
      const t = setTimeout(() => onClose(), 1500);
      return () => clearTimeout(t);
    } else {
      const t = setTimeout(() => {
        // Failed field'ları vurgula, form'a dön
        const failFields = new Set<string>();
        for (const c of validateResult.checks) {
          if (c.status === 'failed') {
            for (const rf of c.related_fields) failFields.add(rf);
          }
        }
        setErrorFields(failFields);
        setErrorMsg(validateResult.message);
        setPhase('form');
      }, 2500);
      return () => clearTimeout(t);
    }
  }, [phase, validateResult, onClose]);

  const renderResult = () => {
    if (!validateResult) return null;
    const { validation_status, checks, message, is_fully_ready } = validateResult;
    const tone = validation_status === 'passed' ? 'success' : validation_status === 'partial' ? 'warning' : 'error';
    return (
      <>
        {renderChecks(checks)}
        <div className={`cred-result-msg ${tone}`}>{message}</div>
        {is_fully_ready && (
          <div style={{ fontSize: '12px', color: '#a8a8b8', textAlign: 'center', marginTop: '4px' }}>
            Otomatik kapanıyor...
          </div>
        )}
      </>
    );
  };

  return (
    <div
      className="dsp-modal-overlay"
      role="presentation"
      onClick={closable ? onClose : undefined}
    >
      <div
        className="cred-modal"
        role="dialog"
        aria-modal="true"
        onClick={e => e.stopPropagation()}
      >
        <div className="cred-modal-title">
          {hasAny ? 'Cüzdan Bilgilerini Güncelle' : 'Cüzdan Bilgilerini Girin'}
        </div>

        {/* Form */}
        {(phase === 'form' || phase === 'saving') && (
          <>
            {(['trading', 'signing', 'relayer'] as const).map(group => (
              <div className="cred-group" key={group}>
                <div className="cred-group-label">{GROUP_LABELS[group]}</div>
                {FIELDS.filter(f => f.group === group).map(renderField)}
              </div>
            ))}

            {errorMsg && (
              <div className="cred-result-msg error">{errorMsg}</div>
            )}

            <div className="cred-actions">
              {closable && (
                <button type="button" className="cred-btn secondary" onClick={onClose} disabled={isFormDisabled}>
                  Kapat
                </button>
              )}
              <button
                type="button"
                className="cred-btn primary"
                onClick={handleSave}
                disabled={isFormDisabled}
              >
                {phase === 'saving' ? 'Kaydediliyor...' : buttonLabel}
              </button>
            </div>
          </>
        )}

        {/* Validating spinner */}
        {phase === 'validating' && (
          <div className="cred-spinner">
            <span className="cred-spinner-dot" />
            Bilgiler kontrol ediliyor...
          </div>
        )}

        {/* Result */}
        {phase === 'result' && renderResult()}
      </div>
    </div>
  );
}
