"""BaseClient — shared HTTP foundation with retry, timeout, error classification."""

import asyncio
import logging

import httpx

from backend.auth_clients.errors import (
    ClientError,
    ErrorCategory,
    classify_http_error,
)
from backend.logging_config.service import get_logger

logger = get_logger("auth_clients.base")


class BaseClient:
    """Base HTTP client with retry, backoff, and error classification.

    Not meant to be used directly. Subclass for specific API clients.
    """

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 15.0,
        retry_max: int = 3,
        retry_backoff_base: float = 1.0,
        source_name: str = "base",
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._retry_max = retry_max
        self._retry_backoff_base = retry_backoff_base
        self._source_name = source_name
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                headers=self._build_headers(),
            )
        return self._client

    def _build_headers(self) -> dict[str, str]:
        """Build request headers. Override in subclasses for auth headers."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        json: dict | None = None,
        params: dict | None = None,
    ) -> httpx.Response:
        """Execute an HTTP request with retry and error classification.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: URL path (appended to base_url)
            json: Request body as dict
            params: Query parameters

        Returns:
            httpx.Response on success

        Raises:
            ClientError: Classified error after retries exhausted
        """
        last_error: ClientError | None = None

        for attempt in range(1, self._retry_max + 1):
            try:
                client = await self._get_client()
                response = await client.request(
                    method=method,
                    url=path,
                    json=json,
                    params=params,
                )

                if response.is_success:
                    return response

                # Classify HTTP error
                error = classify_http_error(response.status_code, self._source_name)

                if not error.retryable or attempt == self._retry_max:
                    raise error

                last_error = error

            except httpx.TimeoutException:
                last_error = ClientError(
                    f"Request timeout after {self._timeout}s",
                    category=ErrorCategory.TIMEOUT,
                    retryable=True,
                    source=self._source_name,
                )
                if attempt == self._retry_max:
                    raise last_error

            except httpx.ConnectError as e:
                last_error = ClientError(
                    f"Connection failed: {e}",
                    category=ErrorCategory.NETWORK,
                    retryable=True,
                    source=self._source_name,
                )
                if attempt == self._retry_max:
                    raise last_error

            except ClientError:
                raise

            except Exception as e:
                last_error = ClientError(
                    f"Unexpected error: {e}",
                    category=ErrorCategory.UNKNOWN,
                    retryable=False,
                    source=self._source_name,
                )
                raise last_error

            # Exponential backoff before retry
            wait = self._retry_backoff_base * (2 ** (attempt - 1))
            logger.warning(
                f"Retry {attempt}/{self._retry_max} for {self._source_name} "
                f"after {wait}s — {last_error}",
            )
            await asyncio.sleep(wait)

        # Should not reach here, but safety net
        raise last_error or ClientError(
            "Request failed after all retries",
            category=ErrorCategory.UNKNOWN,
            source=self._source_name,
        )

    async def get(self, path: str, params: dict | None = None) -> httpx.Response:
        """HTTP GET with retry."""
        return await self._request("GET", path, params=params)

    async def post(self, path: str, json: dict | None = None) -> httpx.Response:
        """HTTP POST with retry."""
        return await self._request("POST", path, json=json)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    @property
    def source_name(self) -> str:
        return self._source_name

    @property
    def is_connected(self) -> bool:
        return self._client is not None and not self._client.is_closed
