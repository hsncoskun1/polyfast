"""RelayerClient — authenticated access to Polymarket Relayer API.

Responsibilities:
- Claim operations (event expiry claims)
- Signer type 2 signing

Requires:
- relayer_key
- private_key (for signing)
- funder_address

Does NOT handle:
- Discovery / market data (→ PublicMarketClient)
- Order placement / balance (→ AuthenticatedTradingClient)
"""

from backend.auth_clients.base import BaseClient
from backend.auth_clients.credential_store import CredentialStore
from backend.auth_clients.errors import ClientError, ErrorCategory

RELAYER_API_URL = "https://relayer.polymarket.com"


class RelayerClient(BaseClient):
    """Client for Polymarket Relayer API — claim operations with signer type 2.

    Requires relayer and signing credentials from CredentialStore.
    """

    def __init__(
        self,
        credential_store: CredentialStore,
        base_url: str = RELAYER_API_URL,
        timeout_seconds: float = 30.0,
        retry_max: int = 3,
    ):
        super().__init__(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            retry_max=retry_max,
            source_name="relayer",
        )
        self._credential_store = credential_store

    def _build_headers(self) -> dict[str, str]:
        """Build headers with relayer authentication."""
        headers = super()._build_headers()

        if not self._credential_store.credentials.has_relayer_credentials():
            raise ClientError(
                "Relayer credentials not configured",
                category=ErrorCategory.AUTH,
                retryable=False,
                source=self._source_name,
            )

        headers["Authorization"] = f"Bearer {self._credential_store.get_relayer_key()}"
        return headers

    @property
    def has_credentials(self) -> bool:
        """Check if relayer + signing credentials are available."""
        creds = self._credential_store.credentials
        return creds.has_relayer_credentials() and creds.has_signing_credentials()

    # Claim methods will be added in v0.6.5+ (claim logic)
