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
    """Credential güncelleme — sade 2-alan modeli.

    Kullanıcı sadece private_key + relayer_key girer.
    Backend derive eder: funder_address, api_key, api_secret, api_passphrase.

    Partial update: None = mevcut korunur.
    """
    private_key: str | None = None
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


def _compute_missing_input(private_key: str, relayer_key: str) -> list[str]:
    """Kullanıcının girmesi gereken alanlardan eksik olanları bul."""
    missing = []
    if not private_key:
        missing.append("private_key")
    if not relayer_key:
        missing.append("relayer_key")
    return missing


def _derive_funder_address(private_key: str) -> str:
    """Private key'den Ethereum cüzdan adresi derive et.

    EOA-only: address = Account.from_key(pk).address
    Proxy/Safe wallet bu sürümde desteklenmiyor.
    """
    from eth_account import Account
    pk = private_key
    if not pk.startswith("0x"):
        pk = "0x" + pk
    account = Account.from_key(pk)
    return account.address


def _derive_api_creds(private_key: str, funder_address: str):
    """Private key'den Polymarket CLOB API credential'larını derive et.

    Returns: (api_key, api_secret, api_passphrase) tuple veya hata.
    """
    from py_clob_client.client import ClobClient

    pk = private_key
    if not pk.startswith("0x"):
        pk = "0x" + pk

    client = ClobClient(
        host="https://clob.polymarket.com",
        key=pk,
        chain_id=137,
        signature_type=2,
        funder=funder_address,
    )
    derived = client.create_or_derive_api_creds()
    return derived.api_key, derived.api_secret, derived.api_passphrase


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
    """Credential kaydet — 2 alan + derive akışı.

    Kullanıcı girer: private_key, relayer_key
    Backend derive eder: funder_address, api_key, api_secret, api_passphrase

    EOA-only: proxy/safe wallet bu sürümde desteklenmiyor.
    Plaintext LOGLANMAZ, response'ta DÖNMEZ.
    """
    orch = _get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    # Partial merge: None = mevcut korunsun
    existing = orch.credential_store.credentials
    pk = body.private_key if body.private_key is not None else existing.private_key
    rk = body.relayer_key if body.relayer_key is not None else existing.relayer_key

    # Input validation — missing fields
    missing = _compute_missing_input(pk, rk)
    if not pk:
        return _build_response(
            existing, missing,
            "Private key gerekli",
        )

    # Adım 1: pk hex format check
    pk_clean = pk
    if not pk_clean.startswith("0x"):
        pk_clean = "0x" + pk_clean
    try:
        int(pk_clean[2:], 16)
    except ValueError:
        raise HTTPException(status_code=422, detail="Private key geçersiz hex formatı")
    if len(pk_clean) != 66:
        raise HTTPException(status_code=422, detail="Private key 64 hex karakter olmalı")

    # Adım 2: Funder address derive
    try:
        funder = _derive_funder_address(pk)
    except Exception:
        raise HTTPException(status_code=422, detail="Private key'den cüzdan adresi türetilemedi")

    # Adım 3: API credential derive
    try:
        api_key, api_secret, api_passphrase = _derive_api_creds(pk, funder)
    except Exception as e:
        log_event(
            logger, logging.WARNING,
            f"API credential derive failed: {type(e).__name__}",
            entity_type="credential",
            entity_id="derive_error",
        )
        # Derive başarısız — sadece pk + relayer kaydet, api creds boş
        creds = Credentials(
            private_key=pk,
            funder_address=funder,
            relayer_key=rk,
        )
        orch.credential_store.load(creds)
        return _build_response(
            creds, missing,
            "Cüzdan adresi türetildi ama API anahtarları oluşturulamadı — tekrar deneyin",
        )

    # Adım 4: Tam credential oluştur + kaydet
    creds = Credentials(
        api_key=api_key,
        api_secret=api_secret,
        api_passphrase=api_passphrase,
        private_key=pk,
        funder_address=funder,
        relayer_key=rk,
    )
    orch.credential_store.load(creds)

    # Encrypted persist — restart sonrası otomatik restore için
    try:
        from backend.persistence.credential_persistence import save_encrypted
        save_encrypted(creds)
    except Exception:
        pass  # Persist fail → credential çalışır ama restart'ta kayıp

    # Credential update sonrası balance fetch tetikle
    # ClobClientWrapper._ensure_initialized() version değişikliğini algılayıp SDK reinit yapar
    # BalanceManager.fetch() yeni credential'larla bakiye çeker
    try:
        await orch.balance_manager.fetch()
    except Exception:
        pass  # Balance fetch başarısız olabilir — credential update'i bloklamaz

    # Log — plaintext YOK
    log_event(
        logger, logging.INFO,
        f"Credential updated: derive=OK, "
        f"trading={creds.has_trading_credentials()}, "
        f"signing={creds.has_signing_credentials()}, "
        f"relayer={creds.has_relayer_credentials()}, "
        f"funder={funder[:6]}****, "
        f"version={orch.credential_store.version}",
        entity_type="credential",
        entity_id="update",
    )

    if not missing:
        msg = "Credential kaydedildi — doğrulama bekleniyor"
    else:
        msg = f"Credential kaydedildi — {', '.join(missing)} eksik"

    return _build_response(creds, missing, msg)


# ╔══════════════════════════════════════════════════════════════╗
# ║  Status endpoint                                              ║
# ╚══════════════════════════════════════════════════════════════╝

class CredentialStatusResponse(BaseModel):
    """Credential durumu — 2-alan modeli (private_key + relayer_key).

    has_any: kullanıcı en az 1 input girmiş mi (private_key veya relayer_key)
    missing_fields: kullanıcının girmesi gereken ama eksik olan inputlar
    masked_fields: tüm credential alanları maskeli (derive edilenler dahil)
    """
    has_any: bool                       # private_key dolu mu
    has_trading_api: bool
    has_signing: bool
    has_relayer: bool
    can_place_orders: bool
    can_auto_claim: bool
    validated: bool
    validation_status: str              # "not_run" | "passed" | "partial" | "failed"
    failed_checks: list[str]
    is_fully_ready: bool
    missing_fields: list[str]           # kullanıcı input: ["private_key", "relayer_key"]
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


def _mask_private_key(pk: str) -> str:
    """Private key maskesi: 0x****son4 — kullanıcı dostu format."""
    if not pk:
        return ""
    # Normalize: 0x prefix ekle
    clean = pk if pk.startswith("0x") else "0x" + pk
    if len(clean) <= 8:
        return "0x****"
    return f"0x****{clean[-4:]}"


def _mask_credentials(creds: Credentials) -> dict[str, str]:
    """Tüm credential alanlarını maskele."""
    return {
        "api_key": _mask(creds.api_key),
        "api_secret": "****" if creds.api_secret else "",
        "api_passphrase": "****" if creds.api_passphrase else "",
        "private_key": _mask_private_key(creds.private_key),
        "funder_address": _mask(creds.funder_address, prefix=6, suffix=4),
        "relayer_key": _mask(creds.relayer_key),
    }


@router.get("/credential/status", response_model=CredentialStatusResponse)
async def credential_status():
    """Credential durumu — 2-alan modeli + maskeli gösterim.

    - has_any: kullanıcı private_key girmiş mi (derive edilen alanlar sayılmaz)
    - missing_fields: kullanıcının girmesi gereken inputlar (private_key, relayer_key)
    - masked_fields: tüm alanlar maskeli (plaintext DÖNMEZ)
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

    # has_any: kullanıcı en az private_key girmiş mi
    has_any = bool(creds.private_key)

    # missing_fields: kullanıcı input contract'ına göre (2 alan)
    missing = _compute_missing_input(creds.private_key, creds.relayer_key)

    # is_fully_ready: credential loaded + balance available → startup restore sonrası true olabilir
    balance_ok = orch.balance_manager.available_balance > 0 if hasattr(orch, 'balance_manager') else False
    is_ready = can_place_orders and can_auto_claim and balance_ok and len(missing) == 0

    return CredentialStatusResponse(
        has_any=has_any,
        has_trading_api=has_trading_api,
        has_signing=has_signing,
        has_relayer=has_relayer,
        can_place_orders=can_place_orders,
        can_auto_claim=can_auto_claim,
        validated=balance_ok,
        validation_status="passed" if is_ready else "not_run",
        failed_checks=[],
        is_fully_ready=is_ready,
        missing_fields=missing,
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
            raw = int(result.get("balance", 0))
            usd = raw / 1_000_000  # USDC 6 decimals
            return CheckResult(
                name="trading_api", label="Trading API", status="passed",
                message=f"Bakiye: ${usd:,.2f}",
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
            related_fields=["private_key"],
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
    """Credential doğrulama — 2-alan modeli (trading_api + relayer).

    2 check:
    1. Trading API — SDK derive + balance fetch (private_key'den)
    2. Relayer — relayer_key presence check

    Signing ayrı check değil — derive başarısının parçası.
    Plaintext LOGLANMAZ, response'ta DÖNMEZ.
    """
    orch = _get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    # 2 check çalıştır
    trading_check = await _check_trading_api(orch)
    relayer_check = _check_relayer(orch)

    checks = [trading_check, relayer_check]
    failed = [c.name for c in checks if c.status == "failed"]
    passed_count = sum(1 for c in checks if c.status == "passed")

    # validation_status: 2/2 = passed, 1/2 = partial, 0/2 = failed
    if passed_count == 2:
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
    can_place_orders = has_trading_api and has_signing and trading_check.status == "passed"
    can_auto_claim = can_place_orders and has_relayer and relayer_check.status == "passed"

    # Mesaj
    if is_fully_ready:
        # Bakiye bilgisini trading check mesajından çıkar
        balance_info = ""
        for c in checks:
            if c.name == "trading_api" and c.status == "passed" and "Bakiye:" in c.message:
                balance_info = f" — {c.message}"
        msg = f"Hoş geldiniz!{balance_info}"
    elif validation_status == "partial":
        msg = f"Eksik kontrol: {', '.join(failed)}"
    else:
        msg = "Kontroller başarısız — bilgileri kontrol edin"

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
