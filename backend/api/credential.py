"""Credential action API — save/update credentials.

POST /api/credential/update → credential kaydet + presence check

Güvenlik kuralları (CLAUDE.md):
- Credential plaintext LOGLANMAZ
- Response'ta maskesiz credential DÖNMEZ
- Bu fazda SQLite persist YOK (in-memory only, bilinçli geçici karar)
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.logging_config.service import get_logger, log_event
from backend.auth_clients.credential_store import Credentials

logger = get_logger("api.credential")

router = APIRouter()


class CredentialUpdateRequest(BaseModel):
    """Credential güncelleme — endpoint seviyesinde validation.

    Trading credentials (zorunlu üçlü): api_key, api_secret, api_passphrase
    Signing credentials (opsiyonel): private_key, funder_address
    """
    api_key: str = ""
    api_secret: str = ""
    api_passphrase: str = ""
    private_key: Optional[str] = None
    funder_address: Optional[str] = None


class CredentialUpdateResponse(BaseModel):
    """Credential save sonucu — dürüst semantik.

    valid alanı YOK — yanıltıcı olur.
    validated = gerçek API validation yapıldı mı (bu fazda: false)
    validation_status = not_run | passed | failed (bu fazda: not_run)
    """
    success: bool
    has_trading: bool       # api_key + api_secret + api_passphrase dolu mu
    has_signing: bool       # private_key + funder_address dolu mu
    validated: bool         # gerçek API validation yapıldı mı
    validation_status: str  # "not_run" | "passed" | "failed"
    message: str


def _get_orchestrator():
    """Orchestrator referansını al — main.py'deki global instance."""
    from backend.main import get_orchestrator
    return get_orchestrator()


@router.post("/credential/update", response_model=CredentialUpdateResponse)
async def credential_update(body: CredentialUpdateRequest):
    """Credential kaydet + presence check.

    - Trading credentials: api_key + api_secret + api_passphrase (zorunlu üçlü)
    - Signing credentials: private_key + funder_address (opsiyonel)
    - Gerçek API validation bu fazda YAPILMIYOR (validation_status="not_run")
    - In-memory only — restart sonrası credential kaybolur (bilinçli geçici karar)
    - Plaintext LOGLANMAZ, response'ta DÖNMEZ
    """
    orch = _get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    # En az bir alan dolu olmalı
    if not body.api_key and not body.api_secret and not body.api_passphrase:
        raise HTTPException(
            status_code=422,
            detail="En az bir trading credential alanı gerekli (api_key, api_secret, api_passphrase)",
        )

    # Credentials oluştur
    creds = Credentials(
        api_key=body.api_key,
        api_secret=body.api_secret,
        api_passphrase=body.api_passphrase,
        private_key=body.private_key or "",
        funder_address=body.funder_address or "",
    )

    # CredentialStore'a yükle — version artar, wrapper'lar reinitialize tetikler
    orch.credential_store.load(creds)

    has_trading = creds.has_trading_credentials()
    has_signing = creds.has_signing_credentials()

    # Log — plaintext YOK, sadece durum
    log_event(
        logger, logging.INFO,
        f"Credential updated: has_trading={has_trading}, has_signing={has_signing}, "
        f"version={orch.credential_store.version}",
        entity_type="credential",
        entity_id="update",
    )

    # Mesaj — kullanıcıya anlaşılır, "doğrulandı" DEMİYORUZ
    if has_trading:
        msg = "Credential kaydedildi"
        if not has_signing:
            msg += " (signing bilgileri eksik — live trade için gerekli)"
    else:
        missing = []
        if not body.api_key:
            missing.append("api_key")
        if not body.api_secret:
            missing.append("api_secret")
        if not body.api_passphrase:
            missing.append("api_passphrase")
        msg = f"Eksik credential: {', '.join(missing)}"

    return CredentialUpdateResponse(
        success=True,
        has_trading=has_trading,
        has_signing=has_signing,
        validated=False,            # bu fazda gerçek validation YOK
        validation_status="not_run",  # dürüst semantik
        message=msg,
    )
