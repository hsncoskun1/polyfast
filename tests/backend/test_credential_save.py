"""Tests for credential save/update + status endpoints.

Coverage:
- 6 alan modeli (trading + signing + relayer)
- missing_fields hesabı
- status endpoint: maskeli gösterim, has_any, capability
- capability flags (has_trading_api, has_signing, has_relayer, can_place_orders, can_auto_claim)
- is_fully_ready semantiği (save sonrası: false)
- version increment
- plaintext güvenlik (log/response'ta plaintext yok)
- response model fields
- router endpoint
"""

import pytest

from backend.auth_clients.credential_store import CredentialStore, Credentials


# ── Helpers ──────────────────────────────────────────────────────

def _full_creds() -> Credentials:
    return Credentials(
        api_key="pk_test_123",
        api_secret="sk_test_456",
        api_passphrase="pp_test_789",
        private_key="0xabc123def456",
        funder_address="0x71C7db5a9b2d9e4F",
        relayer_key="rlk_test_001",
    )


def _trading_only() -> Credentials:
    return Credentials(
        api_key="pk_test_123",
        api_secret="sk_test_456",
        api_passphrase="pp_test_789",
    )


def _trading_signing() -> Credentials:
    return Credentials(
        api_key="pk_test_123",
        api_secret="sk_test_456",
        api_passphrase="pp_test_789",
        private_key="0xabc123def456",
        funder_address="0x71C7db5a9b2d9e4F",
    )


# ╔══════════════════════════════════════════════════════════════╗
# ║  Capability flag tests                                        ║
# ╚══════════════════════════════════════════════════════════════╝

class TestCapabilityFlags:

    def test_full_credentials(self):
        """6 alan dolu → tüm capability true."""
        c = _full_creds()
        assert c.has_trading_credentials() is True
        assert c.has_signing_credentials() is True
        assert c.has_relayer_credentials() is True

    def test_trading_only(self):
        """Sadece trading → signing/relayer false."""
        c = _trading_only()
        assert c.has_trading_credentials() is True
        assert c.has_signing_credentials() is False
        assert c.has_relayer_credentials() is False

    def test_trading_signing_no_relayer(self):
        """Trading + signing → can_place_orders ama can_auto_claim false."""
        c = _trading_signing()
        has_t = c.has_trading_credentials()
        has_s = c.has_signing_credentials()
        has_r = c.has_relayer_credentials()
        can_place = has_t and has_s
        can_claim = can_place and has_r
        assert can_place is True
        assert can_claim is False

    def test_empty_credentials(self):
        """Boş credential → hiçbir capability yok."""
        c = Credentials()
        assert c.has_trading_credentials() is False
        assert c.has_signing_credentials() is False
        assert c.has_relayer_credentials() is False


# ╔══════════════════════════════════════════════════════════════╗
# ║  Missing fields tests                                         ║
# ╚══════════════════════════════════════════════════════════════╝

class TestMissingFields:

    def test_no_missing(self):
        """6 alan dolu → missing_fields boş."""
        from backend.api.credential import _compute_missing
        missing = _compute_missing(_full_creds())
        assert missing == []

    def test_all_missing(self):
        """Boş credential → 6 alan eksik."""
        from backend.api.credential import _compute_missing
        missing = _compute_missing(Credentials())
        assert len(missing) == 6
        assert "api_key" in missing
        assert "relayer_key" in missing

    def test_relayer_missing(self):
        """Trading + signing dolu, relayer eksik."""
        from backend.api.credential import _compute_missing
        missing = _compute_missing(_trading_signing())
        assert missing == ["relayer_key"]

    def test_signing_missing(self):
        """Trading dolu, signing + relayer eksik."""
        from backend.api.credential import _compute_missing
        missing = _compute_missing(_trading_only())
        assert "private_key" in missing
        assert "funder_address" in missing
        assert "relayer_key" in missing
        assert len(missing) == 3


# ╔══════════════════════════════════════════════════════════════╗
# ║  is_fully_ready semantik test                                 ║
# ╚══════════════════════════════════════════════════════════════╝

class TestIsFullyReady:

    def test_save_always_not_ready(self):
        """Save endpoint'te is_fully_ready her zaman false (validate not_run)."""
        from backend.api.credential import _build_response, _compute_missing
        creds = _full_creds()
        missing = _compute_missing(creds)
        resp = _build_response(creds, missing, "test")
        assert resp.is_fully_ready is False
        assert resp.validated is False
        assert resp.validation_status == "not_run"

    def test_save_partial_not_ready(self):
        """Eksik alanlarla save → is_fully_ready=false."""
        from backend.api.credential import _build_response, _compute_missing
        creds = _trading_only()
        missing = _compute_missing(creds)
        resp = _build_response(creds, missing, "test")
        assert resp.is_fully_ready is False
        assert resp.can_place_orders is False  # signing eksik
        assert resp.can_auto_claim is False


# ╔══════════════════════════════════════════════════════════════╗
# ║  Version increment tests                                      ║
# ╚══════════════════════════════════════════════════════════════╝

class TestVersionIncrement:

    def test_initial_version_zero(self):
        store = CredentialStore()
        assert store.version == 0

    def test_version_increments(self):
        store = CredentialStore()
        store.load(_full_creds())
        assert store.version == 1
        store.load(_trading_only())
        assert store.version == 2

    def test_load_from_dict_increments(self):
        store = CredentialStore()
        store.load_from_dict({
            "API_KEY": "k", "SECRET": "s", "PASSPHRASE": "p",
            "PRIVATE_KEY": "pk", "FUNDER": "fa", "RELAYER_KEY": "rk",
        })
        assert store.version == 1


# ╔══════════════════════════════════════════════════════════════╗
# ║  Response model tests                                         ║
# ╚══════════════════════════════════════════════════════════════╝

class TestResponseModel:

    def test_response_has_no_valid_field(self):
        """'valid' alanı response model'de YOK."""
        from backend.api.credential import CredentialUpdateResponse
        fields = list(CredentialUpdateResponse.model_fields.keys())
        assert "valid" not in fields

    def test_response_has_required_fields(self):
        """Tüm zorunlu alanlar mevcut."""
        from backend.api.credential import CredentialUpdateResponse
        fields = set(CredentialUpdateResponse.model_fields.keys())
        required = {
            "success", "has_trading_api", "has_signing", "has_relayer",
            "can_place_orders", "can_auto_claim", "is_fully_ready",
            "validated", "validation_status", "missing_fields", "message",
        }
        assert required.issubset(fields)

    def test_response_no_plaintext_credential(self):
        """Response model'de credential alanı YOK."""
        from backend.api.credential import CredentialUpdateResponse
        fields = set(CredentialUpdateResponse.model_fields.keys())
        forbidden = {"api_key", "api_secret", "api_passphrase",
                     "private_key", "funder_address", "relayer_key"}
        assert fields.isdisjoint(forbidden)


# ╔══════════════════════════════════════════════════════════════╗
# ║  Router endpoint tests                                        ║
# ╚══════════════════════════════════════════════════════════════╝

class TestCredentialEndpoint:

    def test_router_registered(self):
        from backend.api.credential import router
        paths = [r.path for r in router.routes]
        assert "/credential/update" in paths

    def test_status_router_registered(self):
        from backend.api.credential import router
        paths = [r.path for r in router.routes]
        assert "/credential/status" in paths

    def test_request_model_has_6_fields(self):
        """Request model 6 alan içerir."""
        from backend.api.credential import CredentialUpdateRequest
        fields = set(CredentialUpdateRequest.model_fields.keys())
        expected = {"api_key", "api_secret", "api_passphrase",
                    "private_key", "funder_address", "relayer_key"}
        assert expected == fields


# ╔══════════════════════════════════════════════════════════════╗
# ║  Masking tests                                                ║
# ╚══════════════════════════════════════════════════════════════╝

class TestMasking:

    def test_mask_normal_string(self):
        """Normal uzunluk → ilk 4 + **** + son 4."""
        from backend.api.credential import _mask
        result = _mask("pk_test_1234567890abcdef")
        assert result.startswith("pk_t")
        assert result.endswith("cdef")
        assert "****" in result
        assert "1234567890" not in result  # plaintext yok

    def test_mask_short_string(self):
        """Kısa string → ****."""
        from backend.api.credential import _mask
        assert _mask("abc") == "****"
        assert _mask("12345678") == "****"

    def test_mask_empty_string(self):
        """Boş string → ""."""
        from backend.api.credential import _mask
        assert _mask("") == ""

    def test_mask_custom_prefix_suffix(self):
        """Custom prefix/suffix."""
        from backend.api.credential import _mask
        result = _mask("0x71C7db5a9b2d9e4F", prefix=6, suffix=4)
        assert result.startswith("0x71C7")
        assert result.endswith("9e4F")
        assert "****" in result

    def test_mask_credentials_full(self):
        """Tam credential → tüm alanlar maskeli."""
        from backend.api.credential import _mask_credentials
        masked = _mask_credentials(_full_creds())
        # Hiçbir alan plaintext olmamalı
        assert masked["api_key"] != "pk_test_123"
        assert masked["api_key"] != ""
        assert masked["private_key"] != "0xabc123def456"
        assert masked["private_key"] != ""
        assert masked["api_passphrase"] == "****"  # her zaman ****
        assert masked["relayer_key"] != "rlk_test_001"
        assert masked["relayer_key"] != ""

    def test_mask_credentials_empty(self):
        """Boş credential → tüm alanlar ""."""
        from backend.api.credential import _mask_credentials
        masked = _mask_credentials(Credentials())
        for field_name, value in masked.items():
            assert value == "", f"{field_name} should be empty, got: {value}"

    def test_mask_credentials_partial(self):
        """Kısmi credential → dolu alanlar maskeli, boş alanlar ""."""
        from backend.api.credential import _mask_credentials
        masked = _mask_credentials(_trading_only())
        assert masked["api_key"] != ""  # dolu → maskeli
        assert masked["private_key"] == ""  # boş → ""
        assert masked["relayer_key"] == ""  # boş → ""

    def test_mask_never_returns_plaintext(self):
        """Maskeli değer orijinal değeri İÇERMEZ (güvenlik)."""
        from backend.api.credential import _mask
        original = "super_secret_key_1234567890"
        masked = _mask(original)
        # Masked value should not contain the full original
        assert original not in masked


# ╔══════════════════════════════════════════════════════════════╗
# ║  Status response model tests                                  ║
# ╚══════════════════════════════════════════════════════════════╝

class TestStatusResponseModel:

    def test_status_response_fields(self):
        """Status response gerekli alanları içerir."""
        from backend.api.credential import CredentialStatusResponse
        fields = set(CredentialStatusResponse.model_fields.keys())
        required = {
            "has_any", "has_trading_api", "has_signing", "has_relayer",
            "can_place_orders", "can_auto_claim", "validated",
            "validation_status", "failed_checks", "is_fully_ready",
            "masked_fields",
        }
        assert required.issubset(fields)

    def test_status_response_no_plaintext(self):
        """Status response'ta plaintext credential alanı YOK."""
        from backend.api.credential import CredentialStatusResponse
        fields = set(CredentialStatusResponse.model_fields.keys())
        forbidden = {"api_key", "api_secret", "api_passphrase",
                     "private_key", "funder_address", "relayer_key"}
        assert fields.isdisjoint(forbidden)

    def test_has_any_false_when_empty(self):
        """Boş store → has_any=false."""
        store = CredentialStore()
        creds = store.credentials
        has_any = bool(
            creds.api_key or creds.api_secret or creds.api_passphrase
            or creds.private_key or creds.funder_address or creds.relayer_key
        )
        assert has_any is False

    def test_has_any_true_when_loaded(self):
        """Credential yüklenmiş → has_any=true."""
        store = CredentialStore()
        store.load(_full_creds())
        creds = store.credentials
        has_any = bool(
            creds.api_key or creds.api_secret or creds.api_passphrase
            or creds.private_key or creds.funder_address or creds.relayer_key
        )
        assert has_any is True

    def test_has_any_true_partial(self):
        """Kısmi credential → has_any=true."""
        store = CredentialStore()
        store.load(Credentials(api_key="only_key"))
        creds = store.credentials
        has_any = bool(creds.api_key or creds.api_secret)
        assert has_any is True


# ╔══════════════════════════════════════════════════════════════╗
# ║  Validate endpoint tests                                      ║
# ╚══════════════════════════════════════════════════════════════╝

class TestValidateResponseModel:

    def test_validate_response_fields(self):
        """Validate response gerekli alanları içerir."""
        from backend.api.credential import CredentialValidateResponse
        fields = set(CredentialValidateResponse.model_fields.keys())
        required = {
            "validated", "validation_status", "checks", "failed_checks",
            "has_trading_api", "has_signing", "has_relayer",
            "can_place_orders", "can_auto_claim", "is_fully_ready", "message",
        }
        assert required.issubset(fields)

    def test_validate_response_no_plaintext(self):
        """Validate response'ta plaintext credential alanı YOK."""
        from backend.api.credential import CredentialValidateResponse
        fields = set(CredentialValidateResponse.model_fields.keys())
        forbidden = {"api_key", "api_secret", "api_passphrase",
                     "private_key", "funder_address", "relayer_key"}
        assert fields.isdisjoint(forbidden)

    def test_validate_router_registered(self):
        from backend.api.credential import router
        paths = [r.path for r in router.routes]
        assert "/credential/validate" in paths


class TestCheckResult:

    def test_check_result_fields(self):
        """CheckResult doğru field'lara sahip."""
        from backend.api.credential import CheckResult
        c = CheckResult(
            name="trading_api", label="Trading API", status="passed",
            message="OK", related_fields=["api_key", "api_secret", "api_passphrase"],
        )
        assert c.name == "trading_api"
        assert c.status == "passed"
        assert len(c.related_fields) == 3

    def test_check_result_failed(self):
        from backend.api.credential import CheckResult
        c = CheckResult(
            name="signing", label="Signing", status="failed",
            message="Private key formatı geçersiz",
            related_fields=["private_key"],
        )
        assert c.status == "failed"
        assert "private_key" in c.related_fields


class TestSigningCheck:

    def _orch(self, pk="", fa=""):
        from unittest.mock import MagicMock
        orch = MagicMock()
        orch.credential_store.credentials = Credentials(private_key=pk, funder_address=fa)
        return orch

    def test_signing_with_prefix_valid(self):
        """0x prefix + 64 hex → passed."""
        from backend.api.credential import _check_signing
        pk = "0x" + "ab" * 32  # 0x + 64 hex = 66 char
        fa = "0x" + "cd" * 20  # 0x + 40 hex = 42 char
        result = _check_signing(self._orch(pk, fa))
        assert result.status == "passed"

    def test_signing_no_prefix_valid(self):
        """0x prefix'siz 64-char hex → normalizasyon + passed."""
        from backend.api.credential import _check_signing
        pk = "ab" * 32  # 64 hex, 0x yok
        fa = "0x" + "cd" * 20
        result = _check_signing(self._orch(pk, fa))
        assert result.status == "passed"
        assert "doğru formatta" in result.message

    def test_signing_missing(self):
        """Signing eksik → failed."""
        from backend.api.credential import _check_signing
        result = _check_signing(self._orch())
        assert result.status == "failed"
        assert "private_key" in result.related_fields

    def test_signing_bad_hex(self):
        """Hex olmayan private key → failed."""
        from backend.api.credential import _check_signing
        result = _check_signing(self._orch("0xNOTHEX!!NOTHEX!!NOTHEX!!NOTHEX!!NOTHEX!!NOTHEX!!NOTHEX!!NOTHEX!!", "0x" + "cd" * 20))
        assert result.status == "failed"
        assert "hex" in result.message

    def test_signing_short_key(self):
        """Kısa private key → failed."""
        from backend.api.credential import _check_signing
        result = _check_signing(self._orch("0xabc", "0x" + "cd" * 20))
        assert result.status == "failed"
        assert "64 hex" in result.message

    def test_signing_long_key(self):
        """Uzun private key → failed."""
        from backend.api.credential import _check_signing
        pk = "0x" + "ab" * 33  # 66 hex = too long
        result = _check_signing(self._orch(pk, "0x" + "cd" * 20))
        assert result.status == "failed"
        assert "64 hex" in result.message

    def test_funder_bad_prefix(self):
        """Funder 0x ile başlamıyor → failed."""
        from backend.api.credential import _check_signing
        pk = "0x" + "ab" * 32
        result = _check_signing(self._orch(pk, "no_prefix_address_here_long_enough"))
        assert result.status == "failed"
        assert "funder_address" in result.related_fields

    def test_funder_wrong_length(self):
        """Funder 42 karakter değil → failed."""
        from backend.api.credential import _check_signing
        pk = "0x" + "ab" * 32
        result = _check_signing(self._orch(pk, "0xshort"))
        assert result.status == "failed"
        assert "42 karakter" in result.message

    def test_funder_bad_hex(self):
        """Funder hex değil → failed."""
        from backend.api.credential import _check_signing
        pk = "0x" + "ab" * 32
        fa = "0x" + "ZZ" * 20  # 42 char ama hex değil
        result = _check_signing(self._orch(pk, fa))
        assert result.status == "failed"
        assert "hex" in result.message

    def test_funder_valid_42char(self):
        """Funder 0x + 40 hex = 42 char → passed."""
        from backend.api.credential import _check_signing
        pk = "0x" + "ab" * 32
        fa = "0x" + "E5beAf12345678901234567890123456789a04B0"  # exactly 42
        result = _check_signing(self._orch(pk, fa))
        assert result.status == "passed"


class TestRelayerCheck:

    def test_relayer_pass(self):
        """Relayer key dolu → passed."""
        from backend.api.credential import _check_relayer
        from unittest.mock import MagicMock
        orch = MagicMock()
        orch.credential_store.credentials = Credentials(relayer_key="rlk_test")
        result = _check_relayer(orch)
        assert result.status == "passed"

    def test_relayer_missing(self):
        """Relayer key boş → failed."""
        from backend.api.credential import _check_relayer
        from unittest.mock import MagicMock
        orch = MagicMock()
        orch.credential_store.credentials = Credentials()
        result = _check_relayer(orch)
        assert result.status == "failed"
        assert "relayer_key" in result.related_fields


class TestValidationStatus:

    def test_all_passed_is_fully_ready(self):
        """3/3 passed → validation_status="passed", is_fully_ready=true."""
        from backend.api.credential import CheckResult
        checks = [
            CheckResult(name="trading_api", label="T", status="passed", message="", related_fields=[]),
            CheckResult(name="signing", label="S", status="passed", message="", related_fields=[]),
            CheckResult(name="relayer", label="R", status="passed", message="", related_fields=[]),
        ]
        passed_count = sum(1 for c in checks if c.status == "passed")
        failed = [c.name for c in checks if c.status == "failed"]
        status = "passed" if passed_count == 3 else "partial" if passed_count > 0 else "failed"
        is_ready = status == "passed"
        assert status == "passed"
        assert is_ready is True
        assert failed == []

    def test_partial_not_ready(self):
        """2/3 passed → validation_status="partial", is_fully_ready=false."""
        from backend.api.credential import CheckResult
        checks = [
            CheckResult(name="trading_api", label="T", status="passed", message="", related_fields=[]),
            CheckResult(name="signing", label="S", status="passed", message="", related_fields=[]),
            CheckResult(name="relayer", label="R", status="failed", message="", related_fields=["relayer_key"]),
        ]
        passed_count = sum(1 for c in checks if c.status == "passed")
        failed = [c.name for c in checks if c.status == "failed"]
        status = "passed" if passed_count == 3 else "partial" if passed_count > 0 else "failed"
        is_ready = status == "passed"
        assert status == "partial"
        assert is_ready is False
        assert failed == ["relayer"]

    def test_all_failed(self):
        """0/3 passed → validation_status="failed"."""
        from backend.api.credential import CheckResult
        checks = [
            CheckResult(name="trading_api", label="T", status="failed", message="", related_fields=[]),
            CheckResult(name="signing", label="S", status="failed", message="", related_fields=[]),
            CheckResult(name="relayer", label="R", status="failed", message="", related_fields=[]),
        ]
        passed_count = sum(1 for c in checks if c.status == "passed")
        status = "passed" if passed_count == 3 else "partial" if passed_count > 0 else "failed"
        is_ready = status == "passed"
        assert status == "failed"
        assert is_ready is False


# ╔══════════════════════════════════════════════════════════════╗
# ║  Partial update tests                                         ║
# ╚══════════════════════════════════════════════════════════════╝

class TestTradingApiErrorClassification:
    """Trading API error handling — category-based messages."""

    @pytest.mark.asyncio
    async def test_trading_auth_error(self):
        """Auth error → 'API anahtarları geçersiz'."""
        from backend.api.credential import _check_trading_api
        from backend.auth_clients.errors import ClientError, ErrorCategory
        from unittest.mock import MagicMock, AsyncMock
        orch = MagicMock()
        orch.credential_store.credentials = Credentials(
            api_key="k", api_secret="s", api_passphrase="p",
        )
        # Mock trading client to raise auth error
        import backend.api.credential as cred_mod
        original = cred_mod.__dict__.get('_check_trading_api')

        # Direct test: mock the import path
        mock_client_cls = MagicMock()
        mock_client_cls.return_value.fetch_balance = AsyncMock(
            side_effect=ClientError("auth fail", category=ErrorCategory.AUTH)
        )
        import backend.auth_clients.trading_client as tc_mod
        old_cls = tc_mod.AuthenticatedTradingClient
        tc_mod.AuthenticatedTradingClient = mock_client_cls
        try:
            result = await _check_trading_api(orch)
            assert result.status == "failed"
            assert "geçersiz" in result.message
        finally:
            tc_mod.AuthenticatedTradingClient = old_cls

    @pytest.mark.asyncio
    async def test_trading_network_error(self):
        """Network error → 'Bağlantı kurulamadı'."""
        from backend.api.credential import _check_trading_api
        from unittest.mock import MagicMock, AsyncMock
        orch = MagicMock()
        orch.credential_store.credentials = Credentials(
            api_key="k", api_secret="s", api_passphrase="p",
        )
        mock_client_cls = MagicMock()
        mock_client_cls.return_value.fetch_balance = AsyncMock(
            side_effect=ConnectionError("connection refused")
        )
        import backend.auth_clients.trading_client as tc_mod
        old_cls = tc_mod.AuthenticatedTradingClient
        tc_mod.AuthenticatedTradingClient = mock_client_cls
        try:
            result = await _check_trading_api(orch)
            assert result.status == "failed"
            assert "Bağlantı" in result.message
        finally:
            tc_mod.AuthenticatedTradingClient = old_cls

    @pytest.mark.asyncio
    async def test_trading_timeout_error(self):
        """Timeout → 'zaman aşımı'."""
        from backend.api.credential import _check_trading_api
        from unittest.mock import MagicMock, AsyncMock
        import asyncio as aio
        orch = MagicMock()
        orch.credential_store.credentials = Credentials(
            api_key="k", api_secret="s", api_passphrase="p",
        )
        mock_client_cls = MagicMock()
        mock_client_cls.return_value.fetch_balance = AsyncMock(
            side_effect=aio.TimeoutError()
        )
        import backend.auth_clients.trading_client as tc_mod
        old_cls = tc_mod.AuthenticatedTradingClient
        tc_mod.AuthenticatedTradingClient = mock_client_cls
        try:
            result = await _check_trading_api(orch)
            assert result.status == "failed"
            assert "zaman aşımı" in result.message.lower()
        finally:
            tc_mod.AuthenticatedTradingClient = old_cls

    @pytest.mark.asyncio
    async def test_trading_success(self):
        """Başarılı balance fetch → passed."""
        from backend.api.credential import _check_trading_api
        from unittest.mock import MagicMock, AsyncMock
        orch = MagicMock()
        orch.credential_store.credentials = Credentials(
            api_key="k", api_secret="s", api_passphrase="p",
        )
        mock_client_cls = MagicMock()
        mock_client_cls.return_value.fetch_balance = AsyncMock(
            return_value={"balance": "100.00"}
        )
        import backend.auth_clients.trading_client as tc_mod
        old_cls = tc_mod.AuthenticatedTradingClient
        tc_mod.AuthenticatedTradingClient = mock_client_cls
        try:
            result = await _check_trading_api(orch)
            assert result.status == "passed"
            assert "başarılı" in result.message
        finally:
            tc_mod.AuthenticatedTradingClient = old_cls

    @pytest.mark.asyncio
    async def test_trading_missing_creds(self):
        """Credential eksik → failed (API call yapılmaz)."""
        from backend.api.credential import _check_trading_api
        from unittest.mock import MagicMock
        orch = MagicMock()
        orch.credential_store.credentials = Credentials()
        result = await _check_trading_api(orch)
        assert result.status == "failed"
        assert "eksik" in result.message


class TestPartialUpdate:
    """credential/update partial update semantiği:
    None = dokunulmadı → mevcut korunur
    "" = bilinçli boşaltıldı
    "val" = yeni değer
    """

    def test_none_preserves_existing(self):
        """None gönderilen alanlar mevcut değeri korur."""
        store = CredentialStore()
        store.load(Credentials(
            api_key="existing_key",
            api_secret="existing_secret",
            api_passphrase="existing_pass",
            private_key="0xabc",
            funder_address="0xfunder",
            relayer_key="rlk_old",
        ))
        existing = store.credentials

        # Partial merge simülasyonu (endpoint mantığı)
        from backend.api.credential import CredentialUpdateRequest
        body = CredentialUpdateRequest(api_key="new_key")  # sadece api_key

        merged = Credentials(
            api_key=body.api_key if body.api_key is not None else existing.api_key,
            api_secret=body.api_secret if body.api_secret is not None else existing.api_secret,
            api_passphrase=body.api_passphrase if body.api_passphrase is not None else existing.api_passphrase,
            private_key=body.private_key if body.private_key is not None else existing.private_key,
            funder_address=body.funder_address if body.funder_address is not None else existing.funder_address,
            relayer_key=body.relayer_key if body.relayer_key is not None else existing.relayer_key,
        )

        assert merged.api_key == "new_key"           # güncellendi
        assert merged.api_secret == "existing_secret"  # korundu
        assert merged.api_passphrase == "existing_pass"  # korundu
        assert merged.private_key == "0xabc"           # korundu
        assert merged.relayer_key == "rlk_old"         # korundu

    def test_empty_string_clears_field(self):
        """Boş string gönderilen alan bilinçli boşaltılır."""
        store = CredentialStore()
        store.load(Credentials(api_key="existing_key", api_secret="existing_secret"))
        existing = store.credentials

        from backend.api.credential import CredentialUpdateRequest
        body = CredentialUpdateRequest(api_key="")  # bilinçli boşalt

        merged_key = body.api_key if body.api_key is not None else existing.api_key
        assert merged_key == ""  # boşaltıldı

    def test_full_update_overwrites_all(self):
        """Tüm alanlar gönderilirse tümü güncellenir."""
        store = CredentialStore()
        store.load(_full_creds())
        existing = store.credentials

        from backend.api.credential import CredentialUpdateRequest
        body = CredentialUpdateRequest(
            api_key="new_k", api_secret="new_s", api_passphrase="new_p",
            private_key="0xnew", funder_address="0xnewfunder", relayer_key="rlk_new",
        )

        merged = Credentials(
            api_key=body.api_key if body.api_key is not None else existing.api_key,
            api_secret=body.api_secret if body.api_secret is not None else existing.api_secret,
            api_passphrase=body.api_passphrase if body.api_passphrase is not None else existing.api_passphrase,
            private_key=body.private_key if body.private_key is not None else existing.private_key,
            funder_address=body.funder_address if body.funder_address is not None else existing.funder_address,
            relayer_key=body.relayer_key if body.relayer_key is not None else existing.relayer_key,
        )

        assert merged.api_key == "new_k"
        assert merged.api_secret == "new_s"
        assert merged.relayer_key == "rlk_new"

    def test_no_fields_sent_preserves_all(self):
        """Hiç alan gönderilmezse tümü korunur."""
        store = CredentialStore()
        store.load(_full_creds())
        existing = store.credentials

        from backend.api.credential import CredentialUpdateRequest
        body = CredentialUpdateRequest()  # hiçbir alan yok (tümü None)

        merged = Credentials(
            api_key=body.api_key if body.api_key is not None else existing.api_key,
            api_secret=body.api_secret if body.api_secret is not None else existing.api_secret,
            api_passphrase=body.api_passphrase if body.api_passphrase is not None else existing.api_passphrase,
            private_key=body.private_key if body.private_key is not None else existing.private_key,
            funder_address=body.funder_address if body.funder_address is not None else existing.funder_address,
            relayer_key=body.relayer_key if body.relayer_key is not None else existing.relayer_key,
        )

        assert merged.api_key == "pk_test_123"
        assert merged.api_secret == "sk_test_456"
        assert merged.relayer_key == "rlk_test_001"

    def test_request_model_defaults_none(self):
        """Request model'de tüm alanlar default None."""
        from backend.api.credential import CredentialUpdateRequest
        body = CredentialUpdateRequest()
        assert body.api_key is None
        assert body.api_secret is None
        assert body.api_passphrase is None
        assert body.private_key is None
        assert body.funder_address is None
        assert body.relayer_key is None

    def test_single_field_update(self):
        """Tek alan güncelleme — diğerleri None kalır."""
        from backend.api.credential import CredentialUpdateRequest
        body = CredentialUpdateRequest(relayer_key="new_rlk")
        assert body.relayer_key == "new_rlk"
        assert body.api_key is None  # dokunulmadı
        assert body.private_key is None  # dokunulmadı
