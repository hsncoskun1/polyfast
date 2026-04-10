"""Credential security tests — plaintext sızıntı kontrolleri.

Coverage:
- Response model'lerde plaintext credential field YOK
- Log masking filter çalışıyor
- Exception path'te secret sızmıyor
- Mask helpers doğru çalışıyor
- sanitize_error credential sızdırmıyor
"""

import logging

import pytest

from backend.auth_clients.credential_store import Credentials


# ╔══════════════════════════════════════════════════════════════╗
# ║  Response model redaction tests                               ║
# ╚══════════════════════════════════════════════════════════════╝

class TestResponseRedaction:
    """Hiçbir response model'de plaintext credential field olmamalı."""

    _FORBIDDEN = {"api_key", "api_secret", "api_passphrase",
                  "private_key", "funder_address", "relayer_key",
                  "secret", "password", "token"}

    def test_update_response_no_plaintext(self):
        from backend.api.credential import CredentialUpdateResponse
        fields = set(CredentialUpdateResponse.model_fields.keys())
        assert fields.isdisjoint(self._FORBIDDEN)

    def test_status_response_no_plaintext(self):
        from backend.api.credential import CredentialStatusResponse
        fields = set(CredentialStatusResponse.model_fields.keys())
        # masked_fields var ama plaintext değil — key/value kontrolü
        forbidden_direct = self._FORBIDDEN - {"masked_fields"}
        assert fields.isdisjoint(forbidden_direct)

    def test_validate_response_no_plaintext(self):
        from backend.api.credential import CredentialValidateResponse
        fields = set(CredentialValidateResponse.model_fields.keys())
        assert fields.isdisjoint(self._FORBIDDEN)

    def test_check_result_no_plaintext(self):
        from backend.api.credential import CheckResult
        fields = set(CheckResult.model_fields.keys())
        assert fields.isdisjoint(self._FORBIDDEN)


# ╔══════════════════════════════════════════════════════════════╗
# ║  Mask helper tests                                            ║
# ╚══════════════════════════════════════════════════════════════╝

class TestMaskHelpers:

    def test_mask_string_hides_credential(self):
        from backend.logging_config.filters import mask_string
        text = 'api_key="super_secret_key_12345678"'
        masked = mask_string(text)
        assert "super_secret_key_12345678" not in masked
        assert "****" in masked

    def test_mask_string_hides_private_key(self):
        from backend.logging_config.filters import mask_string
        text = 'private_key=0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890'
        masked = mask_string(text)
        assert "abcdef1234567890" not in masked

    def test_mask_dict_hides_fields(self):
        from backend.logging_config.filters import mask_dict
        data = {
            "api_key": "my_super_secret_api_key",
            "status": "ok",
            "private_key": "0xabcdef",
        }
        masked = mask_dict(data)
        assert masked["api_key"] != "my_super_secret_api_key"
        assert "****" in masked["api_key"]
        assert masked["status"] == "ok"  # normal field korunur
        assert masked["private_key"] != "0xabcdef"

    def test_mask_empty_string(self):
        from backend.logging_config.filters import mask_string
        assert mask_string("") == ""

    def test_mask_no_credential(self):
        from backend.logging_config.filters import mask_string
        text = "Balance fetch completed successfully"
        assert mask_string(text) == text  # değişmemeli


class TestMaskCredentials:

    def test_full_credentials_masked(self):
        from backend.api.credential import _mask_credentials
        creds = Credentials(
            api_key="pk_super_secret_long_key_123",
            api_secret="sk_another_secret_456",
            api_passphrase="my_passphrase_here",
            private_key="0xabcdef1234567890abcdef1234567890",
            funder_address="0x71C7db5a9b2d9e4F1234567890abcdef",
            relayer_key="rlk_relayer_secret_key_789",
        )
        masked = _mask_credentials(creds)

        # Plaintext değerler dönmemeli
        for field, original in [
            ("api_key", "pk_super_secret_long_key_123"),
            ("private_key", "0xabcdef1234567890abcdef1234567890"),
            ("relayer_key", "rlk_relayer_secret_key_789"),
        ]:
            assert original not in masked[field], f"{field} plaintext sızdı!"
            assert masked[field] != ""  # boş da olmamalı

        # api_secret/passphrase tamamen gizli
        assert masked["api_secret"] == "****" or "****" in masked["api_secret"]
        assert masked["api_passphrase"] == "****"

    def test_empty_credentials_safe(self):
        from backend.api.credential import _mask_credentials
        masked = _mask_credentials(Credentials())
        for v in masked.values():
            assert v == ""  # boş alan = boş string


# ╔══════════════════════════════════════════════════════════════╗
# ║  Log filter integration tests                                 ║
# ╚══════════════════════════════════════════════════════════════╝

class TestLogFilter:

    def test_credential_masking_filter_masks_message(self):
        from backend.logging_config.filters import CredentialMaskingFilter
        f = CredentialMaskingFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg='api_key="real_secret_value_here_long"',
            args=None, exc_info=None,
        )
        f.filter(record)
        assert "real_secret_value_here_long" not in record.msg
        assert "****" in record.msg

    def test_credential_masking_filter_masks_eth_address(self):
        from backend.logging_config.filters import CredentialMaskingFilter
        f = CredentialMaskingFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg='private_key=0xabcdef1234567890abcdef1234567890abcdef1234567890',
            args=None, exc_info=None,
        )
        f.filter(record)
        assert "abcdef1234567890abcdef1234567890" not in record.msg

    def test_credential_masking_filter_preserves_normal(self):
        from backend.logging_config.filters import CredentialMaskingFilter
        f = CredentialMaskingFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Normal log message without secrets",
            args=None, exc_info=None,
        )
        f.filter(record)
        assert record.msg == "Normal log message without secrets"


# ╔══════════════════════════════════════════════════════════════╗
# ║  sanitize_error tests                                         ║
# ╚══════════════════════════════════════════════════════════════╝

class TestSanitizeError:

    def test_sanitize_hides_credential_in_exception(self):
        from backend.logging_config.filters import sanitize_error
        err = ValueError('Invalid api_key="super_secret_12345678"')
        result = sanitize_error(err)
        assert "super_secret_12345678" not in result
        assert "ValueError" in result

    def test_sanitize_truncates_long_message(self):
        from backend.logging_config.filters import sanitize_error
        err = RuntimeError("x" * 500)
        result = sanitize_error(err)
        assert len(result) < 250
        assert "..." in result

    def test_sanitize_safe_message(self):
        from backend.logging_config.filters import sanitize_error
        err = ConnectionError("Connection refused")
        result = sanitize_error(err)
        assert "ConnectionError" in result
        assert "refused" in result


# ╔══════════════════════════════════════════════════════════════╗
# ║  Exception path — secret sızmama testleri                    ║
# ╚══════════════════════════════════════════════════════════════╝

class TestExceptionPathSafety:

    def test_client_error_no_credential_leak(self):
        """ClientError mesajında credential olmamalı."""
        from backend.auth_clients.errors import ClientError, ErrorCategory
        err = ClientError(
            "Connection failed: ConnectError",
            category=ErrorCategory.NETWORK,
            source="trading",
        )
        msg = str(err)
        # Credential pattern olmamalı
        assert "api_key" not in msg.lower() or "****" in msg
        assert "secret" not in msg.lower()

    def test_credential_update_request_no_extra_fields(self):
        """Request model'de sadece 2 alan — fazla alan backend'e ulaşamaz."""
        from backend.api.credential import CredentialUpdateRequest
        body = CredentialUpdateRequest(private_key="test", relayer_key="test")
        dumped = body.model_dump()
        assert set(dumped.keys()) == {"private_key", "relayer_key"}
        # Fazla alan yok
        assert "api_key" not in dumped
        assert "api_secret" not in dumped
