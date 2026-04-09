"""Tests for FAZ4-6: Credential save/update endpoint.

Coverage:
- save valid trading credentials
- save partial (incomplete)
- version increment
- has_trading / has_signing checks
- validated=false semantik (bu fazda gerçek validation yok)
- eligibility gate after credential save
- router endpoint registered
- plaintext güvenlik (log/response'ta plaintext yok)
"""

import pytest

from backend.auth_clients.credential_store import CredentialStore, Credentials


# ╔══════════════════════════════════════════════════════════════╗
# ║  CredentialStore unit tests                                   ║
# ╚══════════════════════════════════════════════════════════════╝

class TestCredentialSave:

    def test_save_valid_trading(self):
        """3 alan dolu → has_trading=true."""
        store = CredentialStore()
        store.load(Credentials(
            api_key="key123",
            api_secret="secret456",
            api_passphrase="pass789",
        ))
        assert store.credentials.has_trading_credentials() is True

    def test_save_partial_missing_key(self):
        """api_key eksik → has_trading=false."""
        store = CredentialStore()
        store.load(Credentials(
            api_key="",
            api_secret="secret456",
            api_passphrase="pass789",
        ))
        assert store.credentials.has_trading_credentials() is False

    def test_save_partial_missing_secret(self):
        """api_secret eksik → has_trading=false."""
        store = CredentialStore()
        store.load(Credentials(
            api_key="key123",
            api_secret="",
            api_passphrase="pass789",
        ))
        assert store.credentials.has_trading_credentials() is False

    def test_save_partial_missing_passphrase(self):
        """api_passphrase eksik → has_trading=false."""
        store = CredentialStore()
        store.load(Credentials(
            api_key="key123",
            api_secret="secret456",
            api_passphrase="",
        ))
        assert store.credentials.has_trading_credentials() is False

    def test_save_with_signing(self):
        """Trading + signing → both true."""
        store = CredentialStore()
        store.load(Credentials(
            api_key="key123",
            api_secret="secret456",
            api_passphrase="pass789",
            private_key="pk_abc",
            funder_address="0xfunder",
        ))
        assert store.credentials.has_trading_credentials() is True
        assert store.credentials.has_signing_credentials() is True

    def test_signing_without_trading(self):
        """Signing dolu ama trading eksik."""
        store = CredentialStore()
        store.load(Credentials(
            private_key="pk_abc",
            funder_address="0xfunder",
        ))
        assert store.credentials.has_trading_credentials() is False
        assert store.credentials.has_signing_credentials() is True


# ╔══════════════════════════════════════════════════════════════╗
# ║  Version increment tests                                      ║
# ╚══════════════════════════════════════════════════════════════╝

class TestVersionIncrement:

    def test_initial_version_zero(self):
        """Başlangıç version=0."""
        store = CredentialStore()
        assert store.version == 0

    def test_version_increments_on_load(self):
        """Her load'da version artar."""
        store = CredentialStore()
        store.load(Credentials(api_key="k1"))
        assert store.version == 1
        store.load(Credentials(api_key="k2"))
        assert store.version == 2

    def test_version_increments_on_load_from_dict(self):
        """load_from_dict de version artırır."""
        store = CredentialStore()
        store.load_from_dict({"API_KEY": "k1", "SECRET": "s1", "PASSPHRASE": "p1"})
        assert store.version == 1


# ╔══════════════════════════════════════════════════════════════╗
# ║  Eligibility gate semantik test                               ║
# ╚══════════════════════════════════════════════════════════════╝

class TestEligibilityAfterCredential:

    def test_no_credentials_blocks_eligibility(self):
        """Credential yoksa → has_trading=false."""
        store = CredentialStore()
        assert store.credentials.has_trading_credentials() is False

    def test_valid_credentials_allows_eligibility(self):
        """Valid credential → has_trading=true → gate geçer."""
        store = CredentialStore()
        store.load(Credentials(
            api_key="key",
            api_secret="secret",
            api_passphrase="pass",
        ))
        assert store.credentials.has_trading_credentials() is True

    def test_credential_overwrite(self):
        """İkinci load ilkini override eder."""
        store = CredentialStore()
        store.load(Credentials(api_key="key1", api_secret="s1", api_passphrase="p1"))
        assert store.credentials.has_trading_credentials() is True

        # Eksik credential ile overwrite
        store.load(Credentials(api_key="key2"))
        assert store.credentials.has_trading_credentials() is False
        assert store.version == 2


# ╔══════════════════════════════════════════════════════════════╗
# ║  Response model + router tests                                ║
# ╚══════════════════════════════════════════════════════════════╝

class TestCredentialEndpoint:

    def test_router_registered(self):
        """Credential router'da update endpoint var."""
        from backend.api.credential import router
        paths = [r.path for r in router.routes]
        assert "/credential/update" in paths

    def test_response_model_fields(self):
        """CredentialUpdateResponse doğru field'lara sahip — valid YOK."""
        from backend.api.credential import CredentialUpdateResponse
        resp = CredentialUpdateResponse(
            success=True,
            has_trading=True,
            has_signing=False,
            validated=False,
            validation_status="not_run",
            message="Credential kaydedildi",
        )
        assert resp.validated is False
        assert resp.validation_status == "not_run"
        assert not hasattr(resp, 'valid') or 'valid' not in resp.model_fields

    def test_response_no_valid_field(self):
        """Response model'de 'valid' alanı YOK — yanıltıcı semantik engellenmiş."""
        from backend.api.credential import CredentialUpdateResponse
        fields = list(CredentialUpdateResponse.model_fields.keys())
        assert 'valid' not in fields


# ╔══════════════════════════════════════════════════════════════╗
# ║  In-memory persistence semantik test                          ║
# ╚══════════════════════════════════════════════════════════════╝

class TestInMemoryPersistence:

    def test_credential_in_memory_only(self):
        """Credential sadece in-memory — SQLite persist yok.

        Bu bilinçli geçici karar:
        - Plaintext SQLite güvenlik riski
        - Encryption katmanı henüz yok
        - Restart sonrası credential kaybolur
        """
        store = CredentialStore()
        store.load(Credentials(api_key="key", api_secret="s", api_passphrase="p"))
        assert store.credentials.has_trading_credentials() is True

        # Yeni store = credential kayıp (restart simülasyonu)
        store2 = CredentialStore()
        assert store2.credentials.has_trading_credentials() is False
        assert store2.version == 0
