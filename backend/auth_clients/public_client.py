"""PublicMarketClient — unauthenticated access to Polymarket public APIs.

Responsibilities:
- Discovery (event listing, market listing)
- Public market data (prices, orderbook snapshots)
- No credentials required

Does NOT handle:
- Order placement (→ AuthenticatedTradingClient)
- Balance queries (→ AuthenticatedTradingClient)
- Claims (→ RelayerClient)
"""

from backend.auth_clients.base import BaseClient

# Polymarket public API endpoints
GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"


class PublicMarketClient(BaseClient):
    """Client for public, unauthenticated Polymarket API access.

    Used for discovery and public market data. No credentials needed.
    """

    def __init__(
        self,
        base_url: str = GAMMA_API_URL,
        timeout_seconds: float = 15.0,
        retry_max: int = 3,
    ):
        super().__init__(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            retry_max=retry_max,
            source_name="public_market",
        )

    # Discovery and market data methods will be added in v0.2.3+ (discovery engine)
    # For now, this class establishes ownership and separation.
