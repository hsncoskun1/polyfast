"""Tests for auth client structure — BaseClient, PublicMarket, Trading, Relayer, CredentialStore."""

import pytest
import httpx
from unittest.mock import AsyncMock, patch

from backend.auth_clients.errors import (
    ClientError,
    ErrorCategory,
    classify_http_error,
)
from backend.auth_clients.credential_store import Credentials, CredentialStore
from backend.auth_clients.base import BaseClient
from backend.auth_clients.public_client import PublicMarketClient
from backend.auth_clients.trading_client import AuthenticatedTradingClient
from backend.auth_clients.relayer_client import RelayerClient


# ===== Error Classification Tests =====

class TestErrorClassification:
    def test_401_is_auth_error(self):
        err = classify_http_error(401, "test")
        assert err.category == ErrorCategory.AUTH
        assert err.retryable is False

    def test_403_is_auth_error(self):
        err = classify_http_error(403, "test")
        assert err.category == ErrorCategory.AUTH

    def test_429_is_rate_limit_and_retryable(self):
        err = classify_http_error(429, "test")
        assert err.category == ErrorCategory.RATE_LIMIT
        assert err.retryable is True

    def test_400_is_validation(self):
        err = classify_http_error(400, "test")
        assert err.category == ErrorCategory.VALIDATION
        assert err.retryable is False

    def test_500_is_server_error_and_retryable(self):
        err = classify_http_error(500, "test")
        assert err.category == ErrorCategory.SERVER
        assert err.retryable is True

    def test_502_is_server_error(self):
        err = classify_http_error(502, "test")
        assert err.category == ErrorCategory.SERVER

    def test_unknown_status_code(self):
        err = classify_http_error(418, "test")
        assert err.category == ErrorCategory.UNKNOWN

    def test_client_error_repr(self):
        err = ClientError("test", ErrorCategory.AUTH, 401, False, "trading")
        r = repr(err)
        assert "auth" in r
        assert "401" in r
        assert "trading" in r


# ===== CredentialStore Tests =====

class TestCredentialStore:
    def test_empty_store_has_no_credentials(self):
        store = CredentialStore()
        assert store.credentials.has_trading_credentials() is False
        assert store.credentials.has_relayer_credentials() is False
        assert store.credentials.has_signing_credentials() is False

    def test_load_credentials(self):
        store = CredentialStore()
        creds = Credentials(
            api_key="test-key",
            api_secret="test-secret",
            api_passphrase="test-pass",
            private_key="test-pk",
            funder_address="0xtest",
            relayer_key="test-relayer",
        )
        store.load(creds)
        assert store.credentials.has_trading_credentials() is True
        assert store.credentials.has_relayer_credentials() is True
        assert store.credentials.has_signing_credentials() is True

    def test_load_from_dict(self):
        store = CredentialStore()
        store.load_from_dict({
            "API_KEY": "k",
            "SECRET": "s",
            "PASSPHRASE": "p",
            "PRIVATE_KEY": "pk",
            "FUNDER": "0xf",
            "RELAYER_KEY": "rk",
        })
        assert store.credentials.api_key == "k"
        assert store.credentials.api_secret == "s"
        assert store.credentials.api_passphrase == "p"
        assert store.credentials.private_key == "pk"
        assert store.credentials.funder_address == "0xf"
        assert store.credentials.relayer_key == "rk"

    def test_trading_headers(self):
        store = CredentialStore()
        store.load(Credentials(api_key="k", api_secret="s", api_passphrase="p"))
        headers = store.get_trading_headers()
        assert headers["POLY_API_KEY"] == "k"
        assert headers["POLY_SIGNATURE"] == "s"
        assert headers["POLY_PASSPHRASE"] == "p"

    def test_partial_credentials_trading_check(self):
        """Trading check fails if any of the 3 fields is missing."""
        c1 = Credentials(api_key="k", api_secret="s")
        assert c1.has_trading_credentials() is False

        c2 = Credentials(api_key="k", api_passphrase="p")
        assert c2.has_trading_credentials() is False

    def test_partial_credentials_signing_check(self):
        """Signing check fails if either private_key or funder is missing."""
        c = Credentials(private_key="pk")
        assert c.has_signing_credentials() is False


# ===== BaseClient Tests =====

class TestBaseClient:
    def test_instantiation(self):
        client = BaseClient(base_url="https://example.com", source_name="test")
        assert client.source_name == "test"
        assert client.is_connected is False

    def test_default_headers(self):
        client = BaseClient(base_url="https://example.com")
        headers = client._build_headers()
        assert headers["Content-Type"] == "application/json"
        assert headers["Accept"] == "application/json"

    async def test_close_when_not_connected(self):
        client = BaseClient(base_url="https://example.com")
        await client.close()  # Should not raise


# ===== PublicMarketClient Tests =====

class TestPublicMarketClient:
    def test_instantiation(self):
        client = PublicMarketClient()
        assert client.source_name == "public_market"
        assert client.is_connected is False

    def test_custom_url(self):
        client = PublicMarketClient(base_url="https://custom.api.com")
        assert client._base_url == "https://custom.api.com"

    def test_no_auth_headers(self):
        """Public client should not include auth headers."""
        client = PublicMarketClient()
        headers = client._build_headers()
        assert "POLY_API_KEY" not in headers
        assert "Authorization" not in headers


# ===== AuthenticatedTradingClient Tests =====

class TestAuthenticatedTradingClient:
    def _make_client(self, with_creds: bool = True) -> AuthenticatedTradingClient:
        store = CredentialStore()
        if with_creds:
            store.load(Credentials(
                api_key="test-key",
                api_secret="test-secret",
                api_passphrase="test-pass",
            ))
        return AuthenticatedTradingClient(credential_store=store)

    def test_instantiation(self):
        client = self._make_client()
        assert client.source_name == "trading"
        assert client.has_credentials is True

    def test_no_credentials_raises_on_headers(self):
        """Building headers without credentials raises ClientError."""
        client = self._make_client(with_creds=False)
        assert client.has_credentials is False
        with pytest.raises(ClientError) as exc_info:
            client._build_headers()
        assert exc_info.value.category == ErrorCategory.AUTH

    def test_auth_headers_included(self):
        """Headers include POLY_API_KEY, POLY_SIGNATURE, POLY_PASSPHRASE."""
        client = self._make_client()
        headers = client._build_headers()
        assert headers["POLY_API_KEY"] == "test-key"
        assert headers["POLY_SIGNATURE"] == "test-secret"
        assert headers["POLY_PASSPHRASE"] == "test-pass"


# ===== RelayerClient Tests =====

class TestRelayerClient:
    def _make_client(self, with_creds: bool = True) -> RelayerClient:
        store = CredentialStore()
        if with_creds:
            store.load(Credentials(
                relayer_key="test-relayer-key",
                private_key="test-pk",
                funder_address="0xtest",
            ))
        return RelayerClient(credential_store=store)

    def test_instantiation(self):
        client = self._make_client()
        assert client.source_name == "relayer"
        assert client.has_credentials is True

    def test_no_credentials_raises_on_headers(self):
        """Building headers without relayer key raises ClientError."""
        client = self._make_client(with_creds=False)
        assert client.has_credentials is False
        with pytest.raises(ClientError) as exc_info:
            client._build_headers()
        assert exc_info.value.category == ErrorCategory.AUTH

    def test_auth_headers_included(self):
        """Headers include Bearer token with relayer key."""
        client = self._make_client()
        headers = client._build_headers()
        assert headers["Authorization"] == "Bearer test-relayer-key"

    def test_has_credentials_requires_both(self):
        """has_credentials requires relayer_key AND signing credentials."""
        store = CredentialStore()
        store.load(Credentials(relayer_key="rk"))  # No signing creds
        client = RelayerClient(credential_store=store)
        assert client.has_credentials is False


# ===== Client Separation Tests =====

class TestClientSeparation:
    """Verify clients are truly separate — no shared state or cross-contamination."""

    def test_different_source_names(self):
        store = CredentialStore()
        public = PublicMarketClient()
        trading = AuthenticatedTradingClient(credential_store=store)
        relayer = RelayerClient(credential_store=store)

        assert public.source_name == "public_market"
        assert trading.source_name == "trading"
        assert relayer.source_name == "relayer"

    def test_different_base_urls(self):
        store = CredentialStore()
        public = PublicMarketClient()
        trading = AuthenticatedTradingClient(credential_store=store)
        relayer = RelayerClient(credential_store=store)

        assert "gamma" in public._base_url
        assert "clob" in trading._base_url
        assert "relayer" in relayer._base_url

    def test_public_needs_no_credentials(self):
        """Public client works without any credentials."""
        public = PublicMarketClient()
        headers = public._build_headers()
        # Should not raise, no auth needed
        assert "Content-Type" in headers

    def test_trading_and_relayer_share_store_not_state(self):
        """Trading and relayer share a CredentialStore but have separate connections."""
        store = CredentialStore()
        store.load(Credentials(
            api_key="k", api_secret="s", api_passphrase="p",
            relayer_key="rk", private_key="pk", funder_address="0xf",
        ))
        trading = AuthenticatedTradingClient(credential_store=store)
        relayer = RelayerClient(credential_store=store)

        # Both have credentials
        assert trading.has_credentials is True
        assert relayer.has_credentials is True

        # But separate connections
        assert trading._client is None
        assert relayer._client is None
        assert trading is not relayer
