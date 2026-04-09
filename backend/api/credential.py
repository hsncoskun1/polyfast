"""Credential action API — save/update credentials.

POST /api/credential/update → 6 alan kaydet + presence check + capability özeti

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
    """Credential güncelleme — 6 alan.

    Trading API (zorunlu üçlü): api_key, api_secret, api_passphrase
    Signing (zorunlu ikili): private_key, funder_address
    Relayer (zorunlu): relayer_key
    """
    api_key: str = ""
    api_secret: str = ""
    api_passphrase: str = ""
    private_key: str = ""
    funder_address: str = ""
    relayer_key: str = ""


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
    """Credential kaydet + presence check + capability özeti.

    - 6 alan: trading (3) + signing (2) + relayer (1)
    - Tümü zorunlu (is_fully_ready için)
    - Gerçek API validation bu endpoint'te YAPILMIYOR
    - In-memory only — restart sonrası credential kaybolur
    - Plaintext LOGLANMAZ, response'ta DÖNMEZ
    """
    orch = _get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    # Credentials oluştur
    creds = Credentials(
        api_key=body.api_key,
        api_secret=body.api_secret,
        api_passphrase=body.api_passphrase,
        private_key=body.private_key,
        funder_address=body.funder_address,
        relayer_key=body.relayer_key,
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
