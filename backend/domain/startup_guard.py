"""StartupGuard — validates preconditions before trading engine can start.

The startup guard ensures that critical preconditions are met before
the trading engine is allowed to operate. If any precondition fails,
trading is blocked and the system produces visible health warnings.

Current preconditions (v0.2.1):
- Balance fetch must succeed (start balance + available balance)

Future preconditions (later versions):
- Credential validation
- Discovery health
- Market data connectivity
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from backend.accounting.balance import BalanceSnapshot
from backend.auth_clients.errors import ClientError
from backend.auth_clients.trading_client import AuthenticatedTradingClient
from backend.logging_config.service import get_logger, log_event

logger = get_logger("startup_guard")


class StartupStatus(str, Enum):
    """Result of startup guard check."""
    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"


class HealthSeverity(str, Enum):
    """Health incident severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class HealthIncident:
    """A health problem detected during startup or runtime."""
    severity: HealthSeverity
    category: str
    message: str
    suggested_action: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class StartupResult:
    """Result of the startup guard check."""
    status: StartupStatus
    balance: BalanceSnapshot | None = None
    trading_allowed: bool = False
    incidents: list[HealthIncident] = field(default_factory=list)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class StartupGuard:
    """Validates startup preconditions and gates trading engine activation.

    If balance fetch fails, trading is NOT allowed and health CRITICAL is produced.
    The system must NOT silently proceed to trade searching.
    """

    def __init__(self, trading_client: AuthenticatedTradingClient):
        self._trading_client = trading_client
        self._result: StartupResult = StartupResult(status=StartupStatus.NOT_RUN)

    async def run(self) -> StartupResult:
        """Execute all startup precondition checks.

        Returns:
            StartupResult with status, balance, and any incidents.
        """
        incidents: list[HealthIncident] = []
        balance: BalanceSnapshot | None = None

        # --- Check 1: Balance fetch ---
        try:
            if not self._trading_client.has_credentials:
                raise ClientError(
                    "Trading credentials not configured",
                    category="auth",
                    retryable=False,
                    source="startup_guard",
                )

            raw = await self._trading_client.fetch_balance()
            balance = BalanceSnapshot.from_api_response(raw)

            log_event(
                logger, logging.INFO,
                f"Balance fetched: total={balance.total}, available={balance.available}",
                entity_type="startup",
                entity_id="balance_fetch",
            )

        except Exception as e:
            log_event(
                logger, logging.CRITICAL,
                f"Balance fetch failed: {e}",
                entity_type="startup",
                entity_id="balance_fetch_failure",
            )

            incidents.append(HealthIncident(
                severity=HealthSeverity.CRITICAL,
                category="accounting",
                message=f"Balance fetch failed: {e}",
                suggested_action="Check API credentials and network connectivity. "
                                 "Trading will not start until balance is fetched.",
            ))

            log_event(
                logger, logging.CRITICAL,
                "Trading engine blocked — balance fetch is a mandatory precondition",
                entity_type="startup",
                entity_id="trading_engine_blocked",
            )

        # --- Determine result ---
        trading_allowed = balance is not None and len(incidents) == 0

        self._result = StartupResult(
            status=StartupStatus.PASSED if trading_allowed else StartupStatus.FAILED,
            balance=balance,
            trading_allowed=trading_allowed,
            incidents=incidents,
        )

        return self._result

    @property
    def result(self) -> StartupResult:
        """Get the last startup check result."""
        return self._result

    @property
    def is_trading_allowed(self) -> bool:
        """Whether trading engine is allowed to operate."""
        return self._result.trading_allowed
