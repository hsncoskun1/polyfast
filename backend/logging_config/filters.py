"""Log filters — credential masking to prevent sensitive data leakage."""

import logging
import re

# Patterns that match credential-like values
_CREDENTIAL_PATTERNS = [
    # API keys, secrets, tokens (hex, base64, UUID-like)
    (re.compile(r'(["\']?(?:api[_-]?key|secret|passphrase|private[_-]?key|relayer[_-]?key|token|password|credential)["\']?\s*[:=]\s*["\']?)([^"\'\s,}{]+)(["\']?)', re.IGNORECASE), r'\1****\3'),
    # Ethereum addresses and private keys (0x... or plain hex >= 40 chars)
    (re.compile(r'(0x[0-9a-fA-F]{6})[0-9a-fA-F]{30,}'), r'\1****'),
    # Base64 strings that look like secrets (20+ chars with = padding)
    (re.compile(r'([A-Za-z0-9+/]{6})[A-Za-z0-9+/]{14,}={0,2}'), None),  # handled specially
]

# Known field names to mask in structured payloads
_SENSITIVE_FIELDS = frozenset({
    "api_key", "api_secret", "secret", "passphrase", "private_key",
    "relayer_key", "funder", "funder_address", "relayer_addr",
    "token", "password", "credential",
})


def mask_string(text: str) -> str:
    """Mask credential-like patterns in a string."""
    for pattern, replacement in _CREDENTIAL_PATTERNS:
        if replacement is not None:
            text = pattern.sub(replacement, text)
    return text


def mask_dict(data: dict) -> dict:
    """Recursively mask sensitive fields in a dictionary."""
    masked = {}
    for key, value in data.items():
        if key.lower() in _SENSITIVE_FIELDS:
            if isinstance(value, str) and len(value) > 4:
                masked[key] = value[:4] + "****"
            else:
                masked[key] = "****"
        elif isinstance(value, dict):
            masked[key] = mask_dict(value)
        elif isinstance(value, str):
            masked[key] = mask_string(value)
        else:
            masked[key] = value
    return masked


def sanitize_error(e: Exception) -> str:
    """Exception'dan güvenli log mesajı üret — plaintext credential sızdırmaz.

    Kullanım: log_event(logger, WARNING, f"İşlem hatası: {sanitize_error(e)}", ...)
    """
    err_type = type(e).__name__
    # Exception mesajını maskele
    msg = mask_string(str(e))
    # Çok uzun mesajları kes
    if len(msg) > 200:
        msg = msg[:200] + "..."
    return f"{err_type}: {msg}"


class CredentialMaskingFilter(logging.Filter):
    """Log filter that masks credential values in log messages and args."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Mask the message
        if isinstance(record.msg, str):
            record.msg = mask_string(record.msg)

        # Mask args if present
        if record.args:
            if isinstance(record.args, dict):
                record.args = mask_dict(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    mask_string(a) if isinstance(a, str) else a
                    for a in record.args
                )

        return True
