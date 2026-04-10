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
.cred-loading-wrap {
  display: flex;
  flex-direction: column;
  gap: 14px;
  align-items: center;
  padding: 24px 12px;
}
.cred-loading-bar {
  width: 100%;
  height: 3px;
  border-radius: 2px;
  background: ${COLOR.surface};
  overflow: hidden;
}
.cred-loading-bar-inner {
  height: 100%;
  width: 40%;
  border-radius: 2px;
  background: ${COLOR.green};
  animation: cred-slide 1.2s ease-in-out infinite;
}
@keyframes cred-slide {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(350%); }
}
.cred-loading-text {
  font-size: 13px;
  color: ${COLOR.textMuted};
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

type FieldKey = 'private_key' | 'relayer_key';

interface FieldDef {
  key: FieldKey;
  label: string;
  hint: string;
  group: 'wallet' | 'relayer';
}

const FIELDS: FieldDef[] = [
  { key: 'private_key', label: 'Private Key', hint: 'Ethereum cüzdan özel anahtarı (64 hex karakter)', group: 'wallet' },
  { key: 'relayer_key', label: 'Relayer Key', hint: 'Otomatik tahsilat için relayer API anahtarı', group: 'relayer' },
];

const GROUP_LABELS: Record<string, string> = {
  wallet: '🔐 Cüzdan',
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
    private_key: '', relayer_key: '',
  });
  const [touched, setTouched] = useState<Record<FieldKey, boolean>>({
    private_key: false, relayer_key: false,
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
      // Mock — 2 alan boşluk kontrolü
      const mockMissing = FIELDS.filter(f => !values[f.key].trim()).map(f => f.key);
      if (mockMissing.length > 0) {
        setErrorFields(new Set(mockMissing));
        setErrorMsg(`Eksik alanlar: ${mockMissing.join(', ')}`);
        setPhase('form');
        return;
      }
      // Private key hex format check
      const pkVal = values.private_key;
      const hexPart = pkVal.startsWith('0x') ? pkVal.slice(2) : pkVal;
      const pkValid = /^[0-9a-fA-F]{64}$/.test(hexPart);

      const checks = [
        {
          name: 'trading_api', label: 'Trading API',
          status: pkValid ? 'passed' as const : 'failed' as const,
          message: pkValid ? 'Bakiye: $100.00' : 'Private key 64 hex karakter olmalı',
          related_fields: ['private_key'],
        },
        {
          name: 'relayer', label: 'Relayer',
          status: 'passed' as const,
          message: 'Mock: Relayer key mevcut',
          related_fields: ['relayer_key'],
        },
      ];
      const failedChecks = checks.filter(c => c.status === 'failed');
      const allPassed = failedChecks.length === 0;
      if (failedChecks.length > 0) {
        setErrorFields(new Set(failedChecks.flatMap(c => c.related_fields)));
      }
      setPhase('result');
      setValidateResult({
        validated: true,
        validation_status: allPassed ? 'passed' : 'partial',
        checks,
        failed_checks: failedChecks.map(c => c.name),
        has_trading_api: pkValid, has_signing: pkValid, has_relayer: true,
        can_place_orders: pkValid, can_auto_claim: pkValid,
        is_fully_ready: allPassed,
        message: allPassed ? 'Hoş geldiniz! — Mock bakiye: $100.00' : `Eksik kontrol: ${failedChecks.length} sorunlu`,
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

  const handleResultAction = useCallback(() => {
    if (!validateResult) return;
    if (validateResult.is_fully_ready) {
      onClose();
    } else {
      // Başarısız — form'a dön, failed alanlar kırmızı kalsın
      const failFields = new Set<string>();
      for (const c of validateResult.checks) {
        if (c.status === 'failed') {
          for (const rf of c.related_fields) failFields.add(rf);
        }
      }
      setErrorFields(failFields);
      setErrorMsg('Sorunlu alanlar var, lütfen işaretli alanları kontrol edin.');
      setPhase('form');
    }
  }, [validateResult, onClose]);

  const renderResult = () => {
    if (!validateResult) return null;
    const { validation_status, checks, message, is_fully_ready } = validateResult;
    const tone = validation_status === 'passed' ? 'success' : validation_status === 'partial' ? 'warning' : 'error';
    return (
      <>
        {renderChecks(checks)}
        <div className={`cred-result-msg ${tone}`}>{message}</div>
        <div className="cred-actions">
          {is_fully_ready ? (
            <button type="button" className="cred-btn primary" onClick={handleResultAction}>
              Devam Et
            </button>
          ) : (
            <button type="button" className="cred-btn secondary" onClick={handleResultAction}>
              Düzelt
            </button>
          )}
        </div>
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
            {(['wallet', 'relayer'] as const).map(group => (
              <div className="cred-group" key={group}>
                <div className="cred-group-label">{GROUP_LABELS[group]}</div>
                {FIELDS.filter(f => f.group === group).map(renderField)}
              </div>
            ))}

            <div style={{ fontSize: '11px', color: '#6e6e80', lineHeight: '1.4' }}>
              Cüzdan adresi ve API anahtarları otomatik oluşturulur. Sadece standart Ethereum cüzdanları desteklenir.
            </div>

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

        {/* Validating — indeterminate loading bar */}
        {phase === 'validating' && (
          <div className="cred-loading-wrap">
            <div className="cred-loading-bar">
              <div className="cred-loading-bar-inner" />
            </div>
            <span className="cred-loading-text">Bilgiler kontrol ediliyor...</span>
          </div>
        )}

        {/* Result */}
        {phase === 'result' && renderResult()}
      </div>
    </div>
  );
}
