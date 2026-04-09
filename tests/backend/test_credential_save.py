"""Tests for credential save/update endpoint.

Coverage:
- 6 alan modeli (trading + signing + relayer)
- missing_fields hesabı
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

    def test_request_model_has_6_fields(self):
        """Request model 6 alan içerir."""
        from backend.api.credential import CredentialUpdateRequest
        fields = set(CredentialUpdateRequest.model_fields.keys())
        expected = {"api_key", "api_secret", "api_passphrase",
                    "private_key", "funder_address", "relayer_key"}
        assert expected == fields
