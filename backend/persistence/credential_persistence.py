"""Encrypted credential persistence — AES encrypted, machine-specific key.

Güvenlik modeli:
- Fernet (AES-128-CBC + HMAC-SHA256) — güvenilir hazır primitive
- Machine-specific key: hostname + user + namespace → PBKDF2 → Fernet key
- Dosya başka cihaza taşınırsa decrypt başarısız olur (tasarım gereği)
- HMAC doğrulanmadan decrypt yapılmaz (Fernet bunu garanti eder)
- Plaintext credential disk'e ASLA yazılmaz
- Decrypt hatası logda secret sızdırmaz

Dosya: data/credentials.enc
"""

import base64
import hashlib
import json
import logging
import os
import platform
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from backend.auth_clients.credential_store import Credentials
from backend.logging_config.service import get_logger, log_event

logger = get_logger("persistence.credential")

# Encrypted file path
DEFAULT_ENC_PATH = Path("data/credentials.enc")

# Key derivation namespace — versiyon değişirse eski dosya açılmaz
_KEY_NAMESPACE = "polyfast-credential-v1"
_KEY_SALT = b"polyfast-machine-key-salt-v1"
_KEY_ITERATIONS = 100_000


def _get_machine_identity() -> str:
    """Machine-specific identity string.

    Bileşenler:
    - hostname (platform.node)
    - OS user (os.getlogin fallback os.environ)
    - Sabit namespace

    Aynı cihaz + aynı kullanıcı = aynı identity.
    Farklı cihaz veya kullanıcı = farklı identity.
    """
    hostname = platform.node() or "unknown-host"

    # os.getlogin() bazı ortamlarda fail edebilir — fallback
    try:
        username = os.getlogin()
    except OSError:
        username = os.environ.get("USERNAME") or os.environ.get("USER") or "unknown-user"

    return f"{hostname}|{username}|{_KEY_NAMESPACE}"


def _derive_key() -> bytes:
    """Machine-specific Fernet key türet.

    PBKDF2-HMAC-SHA256 ile 32-byte key → base64 → Fernet key (44 bytes).
    """
    identity = _get_machine_identity()
    raw_key = hashlib.pbkdf2_hmac(
        'sha256',
        identity.encode('utf-8'),
        _KEY_SALT,
        _KEY_ITERATIONS,
    )
    # Fernet 32-byte key bekler, base64-urlsafe encoded
    return base64.urlsafe_b64encode(raw_key[:32])


def _credentials_to_json(creds: Credentials) -> bytes:
    """Credentials → JSON bytes (encrypt için)."""
    data = {
        "api_key": creds.api_key,
        "api_secret": creds.api_secret,
        "api_passphrase": creds.api_passphrase,
        "private_key": creds.private_key,
        "funder_address": creds.funder_address,
        "relayer_key": creds.relayer_key,
    }
    return json.dumps(data, ensure_ascii=True).encode('utf-8')


def _json_to_credentials(data: bytes) -> Credentials:
    """JSON bytes → Credentials obje."""
    d = json.loads(data.decode('utf-8'))
    return Credentials(
        api_key=d.get("api_key", ""),
        api_secret=d.get("api_secret", ""),
        api_passphrase=d.get("api_passphrase", ""),
        private_key=d.get("private_key", ""),
        funder_address=d.get("funder_address", ""),
        relayer_key=d.get("relayer_key", ""),
    )


def save_encrypted(creds: Credentials, path: Path | None = None) -> bool:
    """Credential'ları encrypted dosyaya kaydet.

    Returns True on success, False on failure.
    Plaintext ASLA disk'e yazılmaz.
    """
    enc_path = path or DEFAULT_ENC_PATH

    try:
        # Dizin yoksa oluştur
        enc_path.parent.mkdir(parents=True, exist_ok=True)

        key = _derive_key()
        f = Fernet(key)
        plaintext = _credentials_to_json(creds)
        encrypted = f.encrypt(plaintext)

        enc_path.write_bytes(encrypted)

        log_event(
            logger, logging.INFO,
            "Credential encrypted and saved",
            entity_type="persistence",
            entity_id="credential_save",
        )
        return True

    except Exception as e:
        log_event(
            logger, logging.WARNING,
            f"Credential save failed: {type(e).__name__}",
            entity_type="persistence",
            entity_id="credential_save_error",
        )
        return False


def load_encrypted(path: Path | None = None) -> Credentials | None:
    """Encrypted credential dosyasından yükle.

    Returns Credentials on success, None on failure.
    Decrypt hatası secret sızdırmaz.
    """
    enc_path = path or DEFAULT_ENC_PATH

    if not enc_path.exists():
        return None

    try:
        key = _derive_key()
        f = Fernet(key)
        encrypted = enc_path.read_bytes()

        # Fernet.decrypt HMAC doğrulaması yapar — tamper edilmişse InvalidToken
        plaintext = f.decrypt(encrypted)
        creds = _json_to_credentials(plaintext)

        log_event(
            logger, logging.INFO,
            "Credential loaded from encrypted storage",
            entity_type="persistence",
            entity_id="credential_load",
        )
        return creds

    except InvalidToken:
        # Farklı cihaz, farklı kullanıcı, veya dosya tamper edilmiş
        log_event(
            logger, logging.WARNING,
            "Credential decrypt failed — machine key mismatch or corrupted file",
            entity_type="persistence",
            entity_id="credential_decrypt_fail",
        )
        return None

    except Exception as e:
        log_event(
            logger, logging.WARNING,
            f"Credential load failed: {type(e).__name__}",
            entity_type="persistence",
            entity_id="credential_load_error",
        )
        return None


def has_encrypted_file(path: Path | None = None) -> bool:
    """Encrypted credential dosyası var mı."""
    return (path or DEFAULT_ENC_PATH).exists()
