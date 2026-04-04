"""Error classification for auth clients — structured failure types."""

from enum import Enum


class ErrorCategory(str, Enum):
    """Classification of client errors for health surfacing."""
    NETWORK = "network"           # Connection timeout, DNS failure, no route
    AUTH = "auth"                  # 401/403, invalid credentials
    RATE_LIMIT = "rate_limit"     # 429, too many requests
    SERVER = "server"             # 5xx server errors
    VALIDATION = "validation"     # 400, bad request, malformed payload
    TIMEOUT = "timeout"           # Request exceeded deadline
    UNKNOWN = "unknown"           # Unclassifiable error


class ClientError(Exception):
    """Structured client error with category and context."""

    def __init__(
        self,
        message: str,
        category: ErrorCategory,
        status_code: int | None = None,
        retryable: bool = False,
        source: str = "",
    ):
        super().__init__(message)
        self.category = category
        self.status_code = status_code
        self.retryable = retryable
        self.source = source

    def __repr__(self) -> str:
        return (
            f"ClientError(category={self.category.value}, "
            f"status={self.status_code}, retryable={self.retryable}, "
            f"source={self.source}, msg={self.args[0]!r})"
        )


def classify_http_error(status_code: int, source: str = "") -> ClientError:
    """Classify an HTTP status code into a structured ClientError."""
    if status_code == 401 or status_code == 403:
        return ClientError(
            f"Authentication failed (HTTP {status_code})",
            category=ErrorCategory.AUTH,
            status_code=status_code,
            retryable=False,
            source=source,
        )
    elif status_code == 429:
        return ClientError(
            f"Rate limited (HTTP {status_code})",
            category=ErrorCategory.RATE_LIMIT,
            status_code=status_code,
            retryable=True,
            source=source,
        )
    elif status_code == 400:
        return ClientError(
            f"Bad request (HTTP {status_code})",
            category=ErrorCategory.VALIDATION,
            status_code=status_code,
            retryable=False,
            source=source,
        )
    elif 500 <= status_code < 600:
        return ClientError(
            f"Server error (HTTP {status_code})",
            category=ErrorCategory.SERVER,
            status_code=status_code,
            retryable=True,
            source=source,
        )
    else:
        return ClientError(
            f"HTTP error (HTTP {status_code})",
            category=ErrorCategory.UNKNOWN,
            status_code=status_code,
            retryable=False,
            source=source,
        )
