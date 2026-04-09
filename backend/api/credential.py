"""Credential action API — save/update + status.

POST /api/credential/update  → 6 alan kaydet + presence check + capability özeti
GET  /api/credential/status  → maskeli alanlar + capability + validation durumu

Güvenlik kuralları (CLAUDE.md):
- Credential plaintext LOGLANMAZ
- Response'ta maskesiz credential DÖNMEZ
- Bu fazda SQLite persist YOK (in-memory only, bilinçli geçici karar)
- Encrypted persistence ileride ayrı adım

Ürün kuralları:
- 6 alan tümü ZORUNLU (is_fully_ready için)
- is_fully_ready = tüm alanlar dolu + validation_status == "passed"
- Save endpoint'te validated=false (validate ayrı endpoint)
- CREDENTIAL GEREKLI'den çıkış = is_fully_ready=true
"""

import asyncio
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.logging_config.service import get_logger, log_event
from backend.auth_clients.credential_store import Credentials

logger = get_logger("api.credential")

router = APIRouter()


# ╔══════════════════════════════════════════════════════════════╗
# ║  Request / Response models                                    ║
# ╚══════════════════════════════════════════════════════════════╝

class CredentialUpdateRequest(BaseModel):
    """Credential güncelleme — partial update.

    Semantik:
    - None  = alan gönderilmedi → mevcut değer korunur
    - ""    = alan bilinçli boşaltıldı → boş yazılır
    - "val" = yeni değer → güncellenir

    Frontend sadece değiştirilen alanları gönderir.
    """
    api_key: str | None = None
    api_secret: str | None = None
    api_passphrase: str | None = None
    private_key: str | None = None
    funder_address: str | None = None
    relayer_key: str | None = None


class CredentialUpdateResponse(BaseModel):
    """Credential save sonucu — dürüst semantik.

    valid alanı YOK — yanıltıcı olur.
    is_fully_ready = save sonrası: false (validate henüz çalışmadı)
    """
    success: bool
    has_trading_api: bool     # api_key + api_secret + api_passphrase dolu mu
    has_signing: bool         # private_key + funder_address dolu mu
    has_relayer: bool         # relayer_key dolu mu
    can_place_orders: bool    # has_trading_api AND has_signing
    can_auto_claim: bool      # can_place_orders AND has_relayer
    is_fully_ready: bool      # save sonrası: false (validate not_run)
    validated: bool           # gerçek API validation yapıldı mı
    validation_status: str    # "not_run" | "passed" | "partial" | "failed"
    missing_fields: list[str] # boş alanlar listesi
    message: str


# ╔══════════════════════════════════════════════════════════════╗
# ║  Helpers                                                      ║
# ╚══════════════════════════════════════════════════════════════╝

def _get_orchestrator():
    """Orchestrator referansını al — main.py'deki global instance."""
    from backend.main import get_orchestrator
    return get_orchestrator()


def _compute_missing(creds: Credentials) -> list[str]:
    """Boş credential alanlarını bul."""
    missing = []
    if not creds.api_key:
        missing.append("api_key")
    if not creds.api_secret:
        missing.append("api_secret")
    if not creds.api_passphrase:
        missing.append("api_passphrase")
    if not creds.private_key:
        missing.append("private_key")
    if not creds.funder_address:
        missing.append("funder_address")
    if not creds.relayer_key:
        missing.append("relayer_key")
    return missing


def _build_response(creds: Credentials, missing: list[str], message: str) -> CredentialUpdateResponse:
    """Response model oluştur — capability hesabı tek yerde."""
    has_trading_api = creds.has_trading_credentials()
    has_signing = creds.has_signing_credentials()
    has_relayer = creds.has_relayer_credentials()
    can_place_orders = has_trading_api and has_signing
    can_auto_claim = can_place_orders and has_relayer

    return CredentialUpdateResponse(
        success=True,
        has_trading_api=has_trading_api,
        has_signing=has_signing,
        has_relayer=has_relayer,
        can_place_orders=can_place_orders,
        can_auto_claim=can_auto_claim,
        is_fully_ready=False,          # save endpoint'te validate çalışmadı
        validated=False,
        validation_status="not_run",
        missing_fields=missing,
        message=message,
    )


# ╔══════════════════════════════════════════════════════════════╗
# ║  Endpoint                                                     ║
# ╚══════════════════════════════════════════════════════════════╝

@router.post("/credential/update", response_model=CredentialUpdateResponse)
async def credential_update(body: CredentialUpdateRequest):
    """Credential kaydet — partial update + presence check + capability özeti.

    Partial update semantiği:
    - None  = alan gönderilmedi → mevcut değer korunur
    - ""    = alan bilinçli boşaltıldı → boş yazılır
    - "val" = yeni değer → güncellenir

    - In-memory only — restart sonrası credential kaybolur
    - Plaintext LOGLANMAZ, response'ta DÖNMEZ
    """
    orch = _get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    # Mevcut credential'ı al (partial update için)
    existing = orch.credential_store.credentials

    # Partial merge: None = mevcut korunsun, değer varsa güncelle
    creds = Credentials(
        api_key=body.api_key if body.api_key is not None else existing.api_key,
        api_secret=body.api_secret if body.api_secret is not None else existing.api_secret,
        api_passphrase=body.api_passphrase if body.api_passphrase is not None else existing.api_passphrase,
        private_key=body.private_key if body.private_key is not None else existing.private_key,
        funder_address=body.funder_address if body.funder_address is not None else existing.funder_address,
        relayer_key=body.relayer_key if body.relayer_key is not None else existing.relayer_key,
    )

    # CredentialStore'a yükle — version artar
    orch.credential_store.load(creds)

    # Missing fields
    missing = _compute_missing(creds)

    # Log — plaintext YOK, sadece capability durumu
    log_event(
        logger, logging.INFO,
        f"Credential updated: trading={creds.has_trading_credentials()}, "
        f"signing={creds.has_signing_credentials()}, "
        f"relayer={creds.has_relayer_credentials()}, "
        f"missing={len(missing)}, version={orch.credential_store.version}",
        entity_type="credential",
        entity_id="update",
    )

    # Mesaj — dürüst, "doğrulandı" DEMİYORUZ
    if not missing:
        msg = "Credential kaydedildi — doğrulama bekleniyor"
    else:
        msg = f"Credential kaydedildi — {len(missing)} eksik alan: {', '.join(missing)}"

    return _build_response(creds, missing, msg)


# ╔══════════════════════════════════════════════════════════════╗
# ║  Status endpoint                                              ║
# ╚══════════════════════════════════════════════════════════════╝

class CredentialStatusResponse(BaseModel):
    """Credential durumu — maskeli alanlar + capability + validation."""
    has_any: bool                       # herhangi bir alan dolu mu
    has_trading_api: bool
    has_signing: bool
    has_relayer: bool
    can_place_orders: bool
    can_auto_claim: bool
    validated: bool
    validation_status: str              # "not_run" | "passed" | "partial" | "failed"
    failed_checks: list[str]            # ["signing", "relayer"] — validate sonrası dolar
    is_fully_ready: bool
    masked_fields: dict[str, str]       # alan adı → maskeli değer


def _mask(value: str, prefix: int = 4, suffix: int = 4) -> str:
    """Credential alanını maskele — plaintext DÖNMEZ.

    Boş alan → "" (doldurulmamış).
    Kısa alan → "****" (prefix+suffix sığmıyorsa).
    Normal alan → ilk N + **** + son N.
    """
    if not value:
        return ""
    if len(value) <= prefix + suffix + 4:
        return "****"
    return value[:prefix] + "****" + value[-suffix:]


def _mask_credentials(creds: Credentials) -> dict[str, str]:
    """Tüm credential alanlarını maskele."""
    return {
        "api_key": _mask(creds.api_key),
        "api_secret": _mask(creds.api_secret, prefix=0, suffix=0) if creds.api_secret else "",
        "api_passphrase": "****" if creds.api_passphrase else "",
        "private_key": _mask(creds.private_key),
        "funder_address": _mask(creds.funder_address, prefix=6, suffix=4),
        "relayer_key": _mask(creds.relayer_key),
    }


@router.get("/credential/status", response_model=CredentialStatusResponse)
async def credential_status():
    """Credential durumu — maskeli gösterim + capability özeti.

    - Plaintext credential DÖNMEZ — sadece maskeli versiyon
    - Frontend Kaydet/Güncelle kararı için has_any kullanır
    - Maskeli alanlar input placeholder'ı olarak gösterilir
    """
    orch = _get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    creds = orch.credential_store.credentials
    has_trading_api = creds.has_trading_credentials()
    has_signing = creds.has_signing_credentials()
    has_relayer = creds.has_relayer_credentials()
    can_place_orders = has_trading_api and has_signing
    can_auto_claim = can_place_orders and has_relayer

    # has_any: herhangi bir alan dolu mu
    has_any = bool(
        creds.api_key or creds.api_secret or creds.api_passphrase
        or creds.private_key or creds.funder_address or creds.relayer_key
    )

    return CredentialStatusResponse(
        has_any=has_any,
        has_trading_api=has_trading_api,
        has_signing=has_signing,
        has_relayer=has_relayer,
        can_place_orders=can_place_orders,
        can_auto_claim=can_auto_claim,
        validated=False,              # status endpoint validate çalıştırmaz
        validation_status="not_run",
        failed_checks=[],
        is_fully_ready=False,         # validate passed olmadan false
        masked_fields=_mask_credentials(creds),
    )


# ╔══════════════════════════════════════════════════════════════╗
# ║  Validate endpoint                                            ║
# ╚══════════════════════════════════════════════════════════════╝

class CheckResult(BaseModel):
    """Tek validation adımının sonucu."""
    name: str                      # "trading_api" | "signing" | "relayer"
    label: str                     # "Trading API" | "Signing" | "Relayer"
    status: str                    # "passed" | "failed" | "skipped"
    message: str                   # insana okunur açıklama
    related_fields: list[str]      # ["api_key", "api_secret", "api_passphrase"]


class CredentialValidateResponse(BaseModel):
    """Validate sonucu — gerçek API check + capability özeti."""
    validated: bool
    validation_status: str         # "passed" | "partial" | "failed"
    checks: list[CheckResult]
    failed_checks: list[str]       # kısayol: ["signing"]
    has_trading_api: bool
    has_signing: bool
    has_relayer: bool
    can_place_orders: bool
    can_auto_claim: bool
    is_fully_ready: bool           # sadece validation_status=="passed" ise true
    message: str


async def _check_trading_api(orch) -> CheckResult:
    """Trading API doğrulaması — SDK derive + balance fetch ile gerçek check.

    Private key'den API credential derive edip balance çekerek doğrular.
    Kullanıcının manuel API key girmesine gerek yok.
    """
    creds = orch.credential_store.credentials
    if not creds.private_key:
        return CheckResult(
            name="trading_api", label="Trading API", status="failed",
            message="Private key eksik",
            related_fields=["private_key"],
        )
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import BalanceAllowanceParams, AssetType

        pk = creds.private_key
        if not pk.startswith("0x"):
            pk = "0x" + pk

        # SDK client oluştur + API key derive et
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=pk,
            chain_id=137,
            signature_type=2,
            funder=creds.funder_address or None,
        )
        derived = client.create_or_derive_api_creds()
        client.set_api_creds(derived)

        # Balance çek — gerçek trading API test
        params = BalanceAllowanceParams(
            asset_type=AssetType.COLLATERAL,
            signature_type=2,
        )
        result = client.get_balance_allowance(params)

        if result and "balance" in result:
            return CheckResult(
                name="trading_api", label="Trading API", status="passed",
                message="API bağlantısı başarılı — bakiye doğrulandı",
                related_fields=["private_key"],
            )
        return CheckResult(
            name="trading_api", label="Trading API", status="failed",
            message="API yanıt verdi ama bakiye alınamadı",
            related_fields=["private_key"],
        )
    except Exception as e:
        # Plaintext credential LOGLANMAZ — sadece hata sınıfı
        from backend.auth_clients.errors import ClientError, ErrorCategory
        msg = "Beklenmeyen hata — tekrar deneyin"
        if isinstance(e, ClientError):
            cat = e.category
            if cat == ErrorCategory.AUTH:
                msg = "API anahtarları geçersiz — bilgileri kontrol edin"
            elif cat == ErrorCategory.NETWORK:
                msg = "Bağlantı kurulamadı — internet bağlantınızı kontrol edin"
            elif cat == ErrorCategory.TIMEOUT:
                msg = "Bağlantı zaman aşımına uğradı — tekrar deneyin"
            elif cat == ErrorCategory.RATE_LIMIT:
                msg = "Çok fazla istek — biraz bekleyip tekrar deneyin"
            elif cat == ErrorCategory.SERVER:
                msg = "Polymarket sunucu hatası — daha sonra tekrar deneyin"
        elif isinstance(e, (TimeoutError, asyncio.TimeoutError)):
            msg = "Bağlantı zaman aşımına uğradı — tekrar deneyin"
        elif isinstance(e, (ConnectionError, OSError)):
            msg = "Bağlantı kurulamadı — internet bağlantınızı kontrol edin"

        # İç log: secret olmadan teknik tip
        log_event(
            logger, logging.WARNING,
            f"Trading API check failed: {type(e).__name__} "
            f"(category={getattr(e, 'category', 'unknown')})",
            entity_type="credential",
            entity_id="validate_trading",
        )

        return CheckResult(
            name="trading_api", label="Trading API", status="failed",
            message=msg,
            related_fields=["api_key", "api_secret", "api_passphrase"],
        )


def _check_signing(orch) -> CheckResult:
    """Signing doğrulaması — private_key normalizasyon + format + funder check."""
    creds = orch.credential_store.credentials
    if not creds.has_signing_credentials():
        return CheckResult(
            name="signing", label="Signing", status="failed",
            message="Signing credential eksik (private_key, funder_address)",
            related_fields=["private_key", "funder_address"],
        )

    # ── Private key: normalize + validate ──
    pk = creds.private_key
    # 0x prefix yoksa ekle (Polymarket key'ler genelde prefix'siz)
    if not pk.startswith("0x"):
        pk = "0x" + pk
    # Hex format check
    try:
        int(pk[2:], 16)
    except ValueError:
        return CheckResult(
            name="signing", label="Signing", status="failed",
            message="Private key geçersiz hex formatı",
            related_fields=["private_key"],
        )
    # Uzunluk check: 0x + 64 hex = 66 total
    if len(pk) != 66:
        return CheckResult(
            name="signing", label="Signing", status="failed",
            message=f"Private key 64 hex karakter olmalı (mevcut: {len(pk) - 2})",
            related_fields=["private_key"],
        )

    # ── Funder address: strict Ethereum address format ──
    fa = creds.funder_address
    if not fa.startswith("0x"):
        return CheckResult(
            name="signing", label="Signing", status="failed",
            message="Funder address 0x ile başlamalı",
            related_fields=["funder_address"],
        )
    if len(fa) != 42:
        return CheckResult(
            name="signing", label="Signing", status="failed",
            message=f"Funder address 42 karakter olmalı (mevcut: {len(fa)})",
            related_fields=["funder_address"],
        )
    try:
        int(fa[2:], 16)
    except ValueError:
        return CheckResult(
            name="signing", label="Signing", status="failed",
            message="Funder address geçersiz hex formatı",
            related_fields=["funder_address"],
        )

    return CheckResult(
        name="signing", label="Signing", status="passed",
        message="İmza bilgileri doğru formatta",
        related_fields=["private_key", "funder_address"],
    )


def _check_relayer(orch) -> CheckResult:
    """Relayer doğrulaması — presence check (gerçek API call ileride)."""
    creds = orch.credential_store.credentials
    if not creds.has_relayer_credentials():
        return CheckResult(
            name="relayer", label="Relayer", status="failed",
            message="Relayer key eksik",
            related_fields=["relayer_key"],
        )
    # Presence check yeterli — gerçek relayer API call ileride eklenecek
    return CheckResult(
        name="relayer", label="Relayer", status="passed",
        message="Relayer key mevcut",
        related_fields=["relayer_key"],
    )


@router.post("/credential/validate", response_model=CredentialValidateResponse)
async def credential_validate():
    """Credential doğrulama — gerçek API check + capability özeti.

    3 adım:
    1. Trading API — fetch_balance ile gerçek API call
    2. Signing — private_key + funder_address format check
    3. Relayer — relayer_key presence check

    Plaintext LOGLANMAZ, response'ta DÖNMEZ.
    """
    orch = _get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    # 3 check çalıştır
    trading_check = await _check_trading_api(orch)
    signing_check = _check_signing(orch)
    relayer_check = _check_relayer(orch)

    checks = [trading_check, signing_check, relayer_check]
    failed = [c.name for c in checks if c.status == "failed"]
    passed_count = sum(1 for c in checks if c.status == "passed")

    # validation_status semantiği
    if passed_count == 3:
        validation_status = "passed"
    elif passed_count == 0:
        validation_status = "failed"
    else:
        validation_status = "partial"

    is_fully_ready = validation_status == "passed"

    # Capability flags
    creds = orch.credential_store.credentials
    has_trading_api = creds.has_trading_credentials()
    has_signing = creds.has_signing_credentials()
    has_relayer = creds.has_relayer_credentials()
    can_place_orders = has_trading_api and has_signing and trading_check.status == "passed" and signing_check.status == "passed"
    can_auto_claim = can_place_orders and has_relayer and relayer_check.status == "passed"

    # Mesaj
    if is_fully_ready:
        msg = "Tüm bilgiler doğrulandı"
    elif validation_status == "partial":
        msg = f"Kısmi doğrulama: {', '.join(failed)} başarısız"
    else:
        msg = "Doğrulama başarısız — bilgileri kontrol edin"

    # Log — plaintext YOK
    log_event(
        logger, logging.INFO,
        f"Credential validate: status={validation_status}, "
        f"failed={failed}, is_fully_ready={is_fully_ready}",
        entity_type="credential",
        entity_id="validate",
    )

    return CredentialValidateResponse(
        validated=True,
        validation_status=validation_status,
        checks=checks,
        failed_checks=failed,
        has_trading_api=has_trading_api,
        has_signing=has_signing,
        has_relayer=has_relayer,
        can_place_orders=can_place_orders,
        can_auto_claim=can_auto_claim,
        is_fully_ready=is_fully_ready,
        message=msg,
    )
