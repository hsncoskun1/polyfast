"""CredentialStore — minimum skeleton for auth client credential access.

This version provides basic in-memory credential storage to support
client instantiation. Full lifecycle (persistence, propagation, rebind)
will be implemented in Faz 3.5.
"""

from dataclasses import dataclass, field


@dataclass
class Credentials:
    """Container for all Polymarket API credentials."""
    api_key: str = ""
    api_secret: str = ""
    api_passphrase: str = ""
    private_key: str = ""
    funder_address: str = ""
    relayer_key: str = ""

    def has_trading_credentials(self) -> bool:
        """Check if trading credentials (api_key, secret, passphrase) are set."""
        return bool(self.api_key and self.api_secret and self.api_passphrase)

    def has_relayer_credentials(self) -> bool:
        """Check if relayer credentials are set."""
        return bool(self.relayer_key)

    def has_signing_credentials(self) -> bool:
        """Check if signing credentials (private_key, funder) are set."""
        return bool(self.private_key and self.funder_address)


class CredentialStore:
    """Minimal in-memory credential store.

    Supports loading credentials and checking availability.
    Full secure storage, masking, persistence, and propagation
    will be added in Faz 3.5 (v0.3.8+).
    """

    def __init__(self) -> None:
        self._credentials = Credentials()

    def load(self, credentials: Credentials) -> None:
        """Load a complete set of credentials."""
        self._credentials = credentials

    def load_from_dict(self, data: dict[str, str]) -> None:
        """Load credentials from a dictionary (e.g., from .env)."""
        self._credentials = Credentials(
            api_key=data.get("API_KEY", ""),
            api_secret=data.get("SECRET", ""),
            api_passphrase=data.get("PASSPHRASE", ""),
            private_key=data.get("PRIVATE_KEY", ""),
            funder_address=data.get("FUNDER", ""),
            relayer_key=data.get("RELAYER_KEY", ""),
        )

    @property
    def credentials(self) -> Credentials:
        return self._credentials

    def get_trading_headers(self) -> dict[str, str]:
        """Build CLOB API auth headers for trading operations."""
        c = self._credentials
        return {
            "POLY_API_KEY": c.api_key,
            "POLY_SIGNATURE": c.api_secret,
            "POLY_PASSPHRASE": c.api_passphrase,
        }

    def get_relayer_key(self) -> str:
        """Get the relayer API key."""
        return self._credentials.relayer_key

    def get_private_key(self) -> str:
        """Get the private key for signing."""
        return self._credentials.private_key

    def get_funder_address(self) -> str:
        """Get the funder address."""
        return self._credentials.funder_address
