"""AuthenticatedTradingClient — authenticated access to Polymarket CLOB API.

Responsibilities:
- Balance queries (start balance, available balance)
- Order placement (Market FOK)
- Order status queries
- Fill queries

Requires:
- api_key
- api_secret (signature)
- api_passphrase

Does NOT handle:
- Discovery / public market data (→ PublicMarketClient)
- Claims (→ RelayerClient)
"""

from backend.auth_clients.base import BaseClient
from backend.auth_clients.credential_store import CredentialStore
from backend.auth_clients.errors import ClientError, ErrorCategory

CLOB_API_URL = "https://clob.polymarket.com"


class AuthenticatedTradingClient(BaseClient):
    """Client for authenticated Polymarket CLOB API operations.

    Requires trading credentials from CredentialStore.
    """

    def __init__(
        self,
        credential_store: CredentialStore,
        base_url: str = CLOB_API_URL,
        timeout_seconds: float = 15.0,
        retry_max: int = 3,
    ):
        super().__init__(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            retry_max=retry_max,
            source_name="trading",
        )
        self._credential_store = credential_store

    def _build_headers(self) -> dict[str, str]:
        """Build headers with trading authentication."""
        headers = super()._build_headers()

        if not self._credential_store.credentials.has_trading_credentials():
            raise ClientError(
                "Trading credentials not configured",
                category=ErrorCategory.AUTH,
                retryable=False,
                source=self._source_name,
            )

        headers.update(self._credential_store.get_trading_headers())
        return headers

    @property
    def has_credentials(self) -> bool:
        """Check if trading credentials are available."""
        return self._credential_store.credentials.has_trading_credentials()

    # Balance, order, fill methods will be added in v0.2.1+ (balance fetch)
    # and v0.5.x (execution engine)
