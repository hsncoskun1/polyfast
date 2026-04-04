"""Tests for startup guard — balance fetch + trading engine gate."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.accounting.balance import BalanceSnapshot
from backend.auth_clients.credential_store import Credentials, CredentialStore
from backend.auth_clients.trading_client import AuthenticatedTradingClient
from backend.auth_clients.errors import ClientError, ErrorCategory
from backend.domain.startup_guard import (
    StartupGuard,
    StartupStatus,
    StartupResult,
    HealthSeverity,
)


def _make_store(with_creds: bool = True) -> CredentialStore:
    store = CredentialStore()
    if with_creds:
        store.load(Credentials(
            api_key="test-key",
            api_secret="test-secret",
            api_passphrase="test-pass",
        ))
    return store


def _make_client(store: CredentialStore | None = None) -> AuthenticatedTradingClient:
    return AuthenticatedTradingClient(
        credential_store=store or _make_store(),
        base_url="https://test.clob.api",
    )


# ===== BalanceSnapshot Tests =====

class TestBalanceSnapshot:
    def test_from_api_response(self):
        data = {"balance": "247.85", "available": "200.00"}
        snap = BalanceSnapshot.from_api_response(data)
        assert snap.total == 247.85
        assert snap.available == 200.00
        assert snap.fetched_at is not None

    def test_from_api_response_missing_fields(self):
        """Missing fields default to 0."""
        snap = BalanceSnapshot.from_api_response({})
        assert snap.total == 0.0
        assert snap.available == 0.0

    def test_from_api_response_string_values(self):
        data = {"balance": "0.50", "available": "0.25"}
        snap = BalanceSnapshot.from_api_response(data)
        assert snap.total == 0.50
        assert snap.available == 0.25

    def test_snapshot_is_frozen(self):
        snap = BalanceSnapshot.from_api_response({"balance": "10", "available": "5"})
        with pytest.raises(AttributeError):
            snap.total = 999


# ===== StartupGuard — Successful Fetch =====

class TestStartupGuardSuccess:
    async def test_balance_fetch_success_allows_trading(self):
        """Successful balance fetch → trading allowed."""
        client = _make_client()
        client.fetch_balance = AsyncMock(return_value={
            "balance": "247.85",
            "available": "200.00",
        })

        guard = StartupGuard(trading_client=client)
        result = await guard.run()

        assert result.status == StartupStatus.PASSED
        assert result.trading_allowed is True
        assert result.balance is not None
        assert result.balance.total == 247.85
        assert result.balance.available == 200.00
        assert len(result.incidents) == 0

    async def test_is_trading_allowed_property(self):
        """is_trading_allowed reflects the result."""
        client = _make_client()
        client.fetch_balance = AsyncMock(return_value={
            "balance": "100.00",
            "available": "80.00",
        })

        guard = StartupGuard(trading_client=client)
        assert guard.is_trading_allowed is False  # before run
        await guard.run()
        assert guard.is_trading_allowed is True  # after successful run


# ===== StartupGuard — Failed Fetch =====

class TestStartupGuardFailure:
    async def test_balance_fetch_failure_blocks_trading(self):
        """Failed balance fetch → trading NOT allowed."""
        client = _make_client()
        client.fetch_balance = AsyncMock(side_effect=ClientError(
            "Connection failed",
            category=ErrorCategory.NETWORK,
            retryable=True,
            source="trading",
        ))

        guard = StartupGuard(trading_client=client)
        result = await guard.run()

        assert result.status == StartupStatus.FAILED
        assert result.trading_allowed is False
        assert result.balance is None
        assert len(result.incidents) == 1

    async def test_failure_produces_critical_health(self):
        """Failed fetch → health incident with CRITICAL severity."""
        client = _make_client()
        client.fetch_balance = AsyncMock(side_effect=ClientError(
            "Auth failed",
            category=ErrorCategory.AUTH,
            retryable=False,
            source="trading",
        ))

        guard = StartupGuard(trading_client=client)
        result = await guard.run()

        incident = result.incidents[0]
        assert incident.severity == HealthSeverity.CRITICAL
        assert incident.category == "accounting"
        assert "Balance fetch failed" in incident.message
        assert "credential" in incident.suggested_action.lower() or "connectivity" in incident.suggested_action.lower()

    async def test_failure_does_not_allow_silent_trade(self):
        """After failure, is_trading_allowed stays False."""
        client = _make_client()
        client.fetch_balance = AsyncMock(side_effect=Exception("Unexpected error"))

        guard = StartupGuard(trading_client=client)
        await guard.run()

        assert guard.is_trading_allowed is False
        assert guard.result.status == StartupStatus.FAILED

    async def test_no_credentials_blocks_trading(self):
        """Missing credentials → trading blocked."""
        store = _make_store(with_creds=False)
        client = _make_client(store=store)

        guard = StartupGuard(trading_client=client)
        result = await guard.run()

        assert result.status == StartupStatus.FAILED
        assert result.trading_allowed is False
        assert len(result.incidents) == 1
        assert result.incidents[0].severity == HealthSeverity.CRITICAL


# ===== StartupGuard — Initial State =====

class TestStartupGuardInitialState:
    def test_initial_status_is_not_run(self):
        """Before run(), status is NOT_RUN."""
        client = _make_client()
        guard = StartupGuard(trading_client=client)
        assert guard.result.status == StartupStatus.NOT_RUN
        assert guard.is_trading_allowed is False

    async def test_result_property_updates_after_run(self):
        client = _make_client()
        client.fetch_balance = AsyncMock(return_value={
            "balance": "50.00", "available": "50.00"
        })

        guard = StartupGuard(trading_client=client)
        await guard.run()
        assert guard.result.status == StartupStatus.PASSED
        assert guard.result.balance.total == 50.00


# ===== Fetch Balance Method =====

class TestFetchBalanceMethod:
    async def test_fetch_balance_calls_get_balance(self):
        """fetch_balance sends GET /balance."""
        client = _make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {"balance": "100", "available": "80"}
        client.get = AsyncMock(return_value=mock_response)

        result = await client.fetch_balance()
        client.get.assert_called_once_with("/balance")
        assert result["balance"] == "100"
