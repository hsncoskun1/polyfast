"""CredentialStore — credential lifecycle with change detection.

Credential lifecycle (v0.7.0):
- load/load_from_dict ile credential yuklenir
- version counter her degisiklikte artar
- Wrapper'lar version'i kontrol eder — degistiyse reinitialize
- Eski credential ile sessiz calisma ENGELLENIR
"""

import logging
from dataclasses import dataclass, field

from backend.logging_config.service import get_logger, log_event

logger = get_logger("auth.credential_store")


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
    """In-memory credential store with change detection.

    version: her load/update'te artar
    Wrapper'lar last_seen_version ile karsilastirir:
    - version degistiyse reinitialize gerekli
    - eski credential ile sessiz calisma engellenir
    """

    def __init__(self) -> None:
        self._credentials = Credentials()
        self._version: int = 0

    def load(self, credentials: Credentials) -> None:
        """Load a complete set of credentials. Version artar."""
        self._credentials = credentials
        self._version += 1
        log_event(
            logger, logging.INFO,
            f"Credentials loaded (version={self._version})",
            entity_type="credential",
            entity_id="store",
        )

    def load_from_dict(self, data: dict[str, str]) -> None:
        """Load credentials from a dictionary (e.g., from .env). Version artar."""
        self._credentials = Credentials(
            api_key=data.get("API_KEY", ""),
            api_secret=data.get("SECRET", ""),
            api_passphrase=data.get("PASSPHRASE", ""),
            private_key=data.get("PRIVATE_KEY", ""),
            funder_address=data.get("FUNDER", ""),
            relayer_key=data.get("RELAYER_KEY", ""),
        )
        self._version += 1
        log_event(
            logger, logging.INFO,
            f"Credentials loaded from dict (version={self._version})",
            entity_type="credential",
            entity_id="store",
        )

    @property
    def credentials(self) -> Credentials:
        return self._credentials

    @property
    def version(self) -> int:
        """Credential version — her degisiklikte artar."""
        return self._version

    def get_trading_headers(self) -> dict[str, str]:
        """Build CLOB API auth headers for trading operations."""
        c = self._credentials
        return {
            "POLY_API_KEY": c.api_key,
            "POLY_SIGNATURE": c.api_secret,
            "POLY_PASSPHRASE": c.api_passphrase,
        }

    def get_relayer_key(self) -> str:
        return self._credentials.relayer_key

    def get_private_key(self) -> str:
        return self._credentials.private_key

    def get_funder_address(self) -> str:
        return self._credentials.funder_address
