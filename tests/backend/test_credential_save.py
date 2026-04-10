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

class TestMissingInput:
    """2-alan modeli: kullanıcı sadece private_key + relayer_key girer."""

    def test_no_missing(self):
        """İki alan da dolu → missing boş."""
        from backend.api.credential import _compute_missing_input
        missing = _compute_missing_input("0x" + "ab" * 32, "rlk_test")
        assert missing == []

    def test_all_missing(self):
        """İki alan da boş → 2 eksik."""
        from backend.api.credential import _compute_missing_input
        missing = _compute_missing_input("", "")
        assert len(missing) == 2
        assert "private_key" in missing
        assert "relayer_key" in missing

    def test_relayer_missing(self):
        """private_key var, relayer yok."""
        from backend.api.credential import _compute_missing_input
        missing = _compute_missing_input("0x" + "ab" * 32, "")
        assert missing == ["relayer_key"]

    def test_pk_missing(self):
        """relayer var, private_key yok."""
        from backend.api.credential import _compute_missing_input
        missing = _compute_missing_input("", "rlk_test")
        assert missing == ["private_key"]


# ╔══════════════════════════════════════════════════════════════╗
# ║  is_fully_ready semantik test                                 ║
# ╚══════════════════════════════════════════════════════════════╝

class TestIsFullyReady:

    def test_save_always_not_ready(self):
        """Save endpoint'te is_fully_ready her zaman false (validate not_run)."""
        from backend.api.credential import _build_response
        creds = _full_creds()
        resp = _build_response(creds, [], "test")
        assert resp.is_fully_ready is False
        assert resp.validated is False
        assert resp.validation_status == "not_run"

    def test_save_partial_not_ready(self):
        """Eksik relayer → is_fully_ready=false."""
        from backend.api.credential import _build_response
        creds = _trading_signing()  # relayer yok
        resp = _build_response(creds, ["relayer_key"], "test")
        assert resp.is_fully_ready is False
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

    def test_request_model_has_2_fields(self):
        """Request model 2 alan içerir (sade model)."""
        from backend.api.credential import CredentialUpdateRequest
        fields = set(CredentialUpdateRequest.model_fields.keys())
        expected = {"private_key", "relayer_key"}
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
        """Status response gerekli alanları içerir (2-alan modeli)."""
        from backend.api.credential import CredentialStatusResponse
        fields = set(CredentialStatusResponse.model_fields.keys())
        required = {
            "has_any", "has_trading_api", "has_signing", "has_relayer",
            "can_place_orders", "can_auto_claim", "validated",
            "validation_status", "failed_checks", "is_fully_ready",
            "missing_fields", "masked_fields",
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
    """2-check modeli: trading_api + relayer."""

    def test_all_passed_is_fully_ready(self):
        """2/2 passed → validation_status="passed", is_fully_ready=true."""
        from backend.api.credential import CheckResult
        checks = [
            CheckResult(name="trading_api", label="T", status="passed", message="", related_fields=[]),
            CheckResult(name="relayer", label="R", status="passed", message="", related_fields=[]),
        ]
        passed_count = sum(1 for c in checks if c.status == "passed")
        failed = [c.name for c in checks if c.status == "failed"]
        status = "passed" if passed_count == 2 else "partial" if passed_count > 0 else "failed"
        is_ready = status == "passed"
        assert status == "passed"
        assert is_ready is True
        assert failed == []

    def test_trading_pass_relayer_fail(self):
        """1/2 passed → validation_status="partial", is_fully_ready=false."""
        from backend.api.credential import CheckResult
        checks = [
            CheckResult(name="trading_api", label="T", status="passed", message="", related_fields=[]),
            CheckResult(name="relayer", label="R", status="failed", message="", related_fields=["relayer_key"]),
        ]
        passed_count = sum(1 for c in checks if c.status == "passed")
        failed = [c.name for c in checks if c.status == "failed"]
        status = "passed" if passed_count == 2 else "partial" if passed_count > 0 else "failed"
        is_ready = status == "passed"
        assert status == "partial"
        assert is_ready is False
        assert failed == ["relayer"]

    def test_trading_fail_relayer_pass(self):
        """1/2 passed (trading fail) → partial."""
        from backend.api.credential import CheckResult
        checks = [
            CheckResult(name="trading_api", label="T", status="failed", message="", related_fields=["private_key"]),
            CheckResult(name="relayer", label="R", status="passed", message="", related_fields=[]),
        ]
        passed_count = sum(1 for c in checks if c.status == "passed")
        status = "passed" if passed_count == 2 else "partial" if passed_count > 0 else "failed"
        assert status == "partial"

    def test_all_failed(self):
        """0/2 passed → validation_status="failed"."""
        from backend.api.credential import CheckResult
        checks = [
            CheckResult(name="trading_api", label="T", status="failed", message="", related_fields=[]),
            CheckResult(name="relayer", label="R", status="failed", message="", related_fields=[]),
        ]
        passed_count = sum(1 for c in checks if c.status == "passed")
        status = "passed" if passed_count == 2 else "partial" if passed_count > 0 else "failed"
        is_ready = status == "passed"
        assert status == "failed"
        assert is_ready is False


# ╔══════════════════════════════════════════════════════════════╗
# ║  Partial update tests                                         ║
# ╚══════════════════════════════════════════════════════════════╝

class TestTradingApiErrorClassification:
    """Trading API error handling — SDK derive + balance based."""

    def _orch_with_pk(self):
        from unittest.mock import MagicMock
        orch = MagicMock()
        orch.credential_store.credentials = Credentials(
            private_key="0x" + "ab" * 32,
            funder_address="0x" + "cd" * 20,
        )
        return orch

    @pytest.mark.asyncio
    async def test_trading_success(self):
        """SDK balance OK → passed."""
        from backend.api.credential import _check_trading_api
        from unittest.mock import patch, MagicMock
        orch = self._orch_with_pk()

        mock_client = MagicMock()
        mock_client.create_or_derive_api_creds.return_value = MagicMock()
        mock_client.get_balance_allowance.return_value = {"balance": "1000"}

        with patch('py_clob_client.client.ClobClient', return_value=mock_client):
            result = await _check_trading_api(orch)
        assert result.status == "passed"
        assert "Bakiye" in result.message

    @pytest.mark.asyncio
    async def test_trading_sdk_error(self):
        """SDK hata → failed."""
        from backend.api.credential import _check_trading_api
        from unittest.mock import patch, MagicMock
        orch = self._orch_with_pk()

        mock_client = MagicMock()
        mock_client.create_or_derive_api_creds.side_effect = Exception("SDK init failed")

        with patch('py_clob_client.client.ClobClient', return_value=mock_client):
            result = await _check_trading_api(orch)
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_trading_network_error(self):
        """ConnectionError → 'Bağlantı kurulamadı'."""
        from backend.api.credential import _check_trading_api
        from unittest.mock import patch, MagicMock
        orch = self._orch_with_pk()

        mock_client = MagicMock()
        mock_client.create_or_derive_api_creds.side_effect = ConnectionError("refused")

        with patch('py_clob_client.client.ClobClient', return_value=mock_client):
            result = await _check_trading_api(orch)
        assert result.status == "failed"
        assert "Bağlantı" in result.message

    @pytest.mark.asyncio
    async def test_trading_missing_pk(self):
        """Private key eksik → failed (SDK call yapılmaz)."""
        from backend.api.credential import _check_trading_api
        from unittest.mock import MagicMock
        orch = MagicMock()
        orch.credential_store.credentials = Credentials()
        result = await _check_trading_api(orch)
        assert result.status == "failed"
        assert "eksik" in result.message.lower() or "Private" in result.message


class TestDeriveHelpers:
    """Funder address + API credential derive testleri."""

    def test_derive_funder_address(self):
        """Private key'den funder address derive edilir."""
        from backend.api.credential import _derive_funder_address
        pk = "0x" + "ab" * 32
        addr = _derive_funder_address(pk)
        assert addr.startswith("0x")
        assert len(addr) == 42

    def test_derive_funder_no_prefix(self):
        """0x prefix'siz pk'den de derive çalışır."""
        from backend.api.credential import _derive_funder_address
        pk = "ab" * 32
        addr = _derive_funder_address(pk)
        assert addr.startswith("0x")
        assert len(addr) == 42

    def test_derive_funder_invalid_pk(self):
        """Geçersiz pk → exception."""
        from backend.api.credential import _derive_funder_address
        with pytest.raises(Exception):
            _derive_funder_address("not_valid_hex")


class TestPartialUpdate2Field:
    """2-alan modeli partial update semantiği."""

    def test_request_model_2_fields(self):
        """Request model'de sadece 2 alan var."""
        from backend.api.credential import CredentialUpdateRequest
        fields = set(CredentialUpdateRequest.model_fields.keys())
        assert fields == {"private_key", "relayer_key"}

    def test_request_defaults_none(self):
        """Boş body → iki alan da None."""
        from backend.api.credential import CredentialUpdateRequest
        body = CredentialUpdateRequest()
        assert body.private_key is None
        assert body.relayer_key is None

    def test_partial_pk_only(self):
        """Sadece pk gönderilirse relayer None kalır."""
        from backend.api.credential import CredentialUpdateRequest
        body = CredentialUpdateRequest(private_key="0x" + "ab" * 32)
        assert body.private_key is not None
        assert body.relayer_key is None

    def test_partial_relayer_only(self):
        """Sadece relayer gönderilirse pk None kalır."""
        from backend.api.credential import CredentialUpdateRequest
        body = CredentialUpdateRequest(relayer_key="rlk_new")
        assert body.relayer_key == "rlk_new"
        assert body.private_key is None
