"""Credential lifecycle tests -- v0.7.0.

CredentialStore version tracking + ClobClientWrapper/RelayerClientWrapper
credential change detection ve reinitialize davranisi.
"""

import pytest
from backend.auth_clients.credential_store import CredentialStore, Credentials
from backend.execution.clob_client_wrapper import ClobClientWrapper
from backend.execution.relayer_client_wrapper import RelayerClientWrapper


class TestCredentialStoreVersion:

    def test_initial_version_zero(self):
        store = CredentialStore()
        assert store.version == 0

    def test_load_increments_version(self):
        store = CredentialStore()
        store.load(Credentials(api_key="k1"))
        assert store.version == 1
        store.load(Credentials(api_key="k2"))
        assert store.version == 2

    def test_load_from_dict_increments_version(self):
        store = CredentialStore()
        store.load_from_dict({"API_KEY": "k1"})
        assert store.version == 1

    def test_credentials_updated_after_load(self):
        store = CredentialStore()
        store.load(Credentials(api_key="old"))
        assert store.credentials.api_key == "old"
        store.load(Credentials(api_key="new"))
        assert store.credentials.api_key == "new"


class TestClobClientCredentialStore:

    def test_string_params_backward_compat(self):
        """String params ile olusturma hala calisiyor."""
        wrapper = ClobClientWrapper(private_key="pk", api_key="ak")
        # initialize denemez cunku SDK yok, ama hata vermez
        assert wrapper._private_key == "pk"

    def test_credential_store_connection(self):
        """CredentialStore ile olusturma."""
        store = CredentialStore()
        store.load(Credentials(
            api_key="k1", api_secret="s1", api_passphrase="p1",
            private_key="pk1",
        ))
        wrapper = ClobClientWrapper(credential_store=store)

        # is_initialized cagrildiginda _ensure_initialized calisiyor
        # SDK yok ama credential'lar cekilmis olmali
        _ = wrapper.is_initialized
        assert wrapper._api_key == "k1"
        assert wrapper._private_key == "pk1"
        assert wrapper._last_cred_version == 1

    def test_credential_change_detected(self):
        """Credential degisince wrapper yeni credential'lari alir."""
        store = CredentialStore()
        store.load(Credentials(api_key="k1", private_key="pk1"))

        wrapper = ClobClientWrapper(credential_store=store)
        _ = wrapper.is_initialized  # ilk sync
        assert wrapper._api_key == "k1"

        # Credential degistir
        store.load(Credentials(api_key="k2", private_key="pk2"))
        assert store.version == 2

        # Sonraki islemde yeni credential alinir
        _ = wrapper.is_initialized
        assert wrapper._api_key == "k2"
        assert wrapper._private_key == "pk2"
        assert wrapper._last_cred_version == 2

    def test_no_change_no_reinitialize(self):
        """Credential degismediyse reinitialize yapilmaz."""
        store = CredentialStore()
        store.load(Credentials(api_key="k1", private_key="pk1"))

        wrapper = ClobClientWrapper(credential_store=store)
        _ = wrapper.is_initialized
        v1 = wrapper._last_cred_version

        # Tekrar cagir — version ayni
        _ = wrapper.is_initialized
        assert wrapper._last_cred_version == v1  # degismedi

    def test_no_store_no_version_tracking(self):
        """CredentialStore yoksa version tracking yok."""
        wrapper = ClobClientWrapper(private_key="pk", api_key="ak")
        wrapper._ensure_initialized()
        assert wrapper._last_cred_version == -1  # degismedi


class TestRelayerClientCredentialStore:

    def test_string_params_backward_compat(self):
        relayer = RelayerClientWrapper(
            private_key="pk", relayer_api_key="rk", relayer_address="0x1",
        )
        assert relayer.is_initialized is True

    def test_credential_store_connection(self):
        store = CredentialStore()
        store.load(Credentials(
            private_key="pk1", relayer_key="rk1", funder_address="0x1",
        ))
        relayer = RelayerClientWrapper(credential_store=store)

        assert relayer.is_initialized is True
        assert relayer._private_key == "pk1"
        assert relayer._relayer_api_key == "rk1"

    def test_credential_change_detected(self):
        store = CredentialStore()
        store.load(Credentials(
            private_key="pk1", relayer_key="rk1", funder_address="0x1",
        ))
        relayer = RelayerClientWrapper(credential_store=store)
        assert relayer.is_initialized is True

        # Credential degistir
        store.load(Credentials(
            private_key="pk2", relayer_key="rk2", funder_address="0x2",
        ))
        # Sonraki islemde yeni credential
        assert relayer.is_initialized is True
        assert relayer._private_key == "pk2"
        assert relayer._relayer_api_key == "rk2"

    def test_credential_removed_uninitializes(self):
        """Credential kaldirilirsa wrapper uninitialized olur."""
        store = CredentialStore()
        store.load(Credentials(
            private_key="pk1", relayer_key="rk1", funder_address="0x1",
        ))
        relayer = RelayerClientWrapper(credential_store=store)
        assert relayer.is_initialized is True

        # Bos credential yukle
        store.load(Credentials())
        assert relayer.is_initialized is False


class TestCredentialLifecycleBoundaries:

    def test_store_not_imported_in_strategy(self):
        """Strategy katmaninda credential import yok."""
        import backend.strategy.engine as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "credential" not in line.lower()

    def test_clob_and_relayer_independent(self):
        """Clob ve relayer ayri store referansi kullanabilir."""
        store = CredentialStore()
        store.load(Credentials(
            api_key="k1", api_secret="s1", api_passphrase="p1",
            private_key="pk1", relayer_key="rk1", funder_address="0x1",
        ))
        clob = ClobClientWrapper(credential_store=store)
        relayer = RelayerClientWrapper(credential_store=store)

        # Ikisi de ayni store'dan beslenebilir
        _ = clob.is_initialized
        _ = relayer.is_initialized
        assert clob._api_key == "k1"
        assert relayer._relayer_api_key == "rk1"
