# Copyright 2026, Jamf Software LLC
"""Jamf Protect GraphQL API Client.

Provides a client for interacting with Jamf Protect's GraphQL API.
Handles authentication and request formatting.
"""

import logging
import re
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx

from .protect_auth import ProtectAuth

logger = logging.getLogger(__name__)


class ProtectAPIError(Exception):
    """Raised when a Jamf Protect API request fails."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        graphql_errors: list[dict] | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.graphql_errors = graphql_errors or []


class ProtectClient:
    """Client for interacting with Jamf Protect GraphQL API.

    Handles authentication and GraphQL query execution.
    """

    # Default timeout for API requests (in seconds)
    DEFAULT_TIMEOUT = 30.0

    def __init__(self, auth: ProtectAuth, timeout: float = DEFAULT_TIMEOUT):
        """Initialize Protect API client.

        Args:
            auth: ProtectAuth instance for handling authentication
            timeout: Request timeout in seconds
        """
        self.auth = auth
        self.base_url = auth.base_url
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @classmethod
    def from_env(cls, timeout: float = DEFAULT_TIMEOUT) -> Optional["ProtectClient"]:
        """Create ProtectClient from environment variables.

        Args:
            timeout: Request timeout in seconds

        Returns:
            Configured ProtectClient instance, or None if not configured
        """
        auth = ProtectAuth.from_env()
        if auth is None:
            return None
        return cls(auth=auth, timeout=timeout)

    @asynccontextmanager
    async def _get_client(self):
        """Get or create HTTP client as async context manager.

        Yields:
            httpx.AsyncClient instance
        """
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)

        yield self._client

    async def close(self):
        """Close the HTTP client and invalidate token."""
        if self._client:
            self.auth.invalidate_token()
            await self._client.aclose()
            self._client = None

    async def query(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query against the Protect API.

        Args:
            query: GraphQL query string
            variables: Optional query variables
            operation_name: Optional operation name for multi-operation queries

        Returns:
            The 'data' portion of the GraphQL response

        Raises:
            ProtectAPIError: If the request fails or GraphQL returns errors
        """
        url = f"{self.base_url}/graphql"

        async with self._get_client() as client:
            token = await self.auth.get_token(client)

            headers = {
                "Authorization": token,
                "Content-Type": "application/json",
            }

            payload: dict[str, Any] = {"query": query}
            if variables:
                payload["variables"] = variables
            if operation_name:
                payload["operationName"] = operation_name

            try:
                response = await client.post(
                    url,
                    json=payload,
                    headers=headers,
                )

                logger.debug(
                    "GraphQL request -> %d",
                    response.status_code,
                )

                response.raise_for_status()

                result = response.json()

                # Check for GraphQL errors
                if "errors" in result and result["errors"]:
                    error_messages = [
                        e.get("message", str(e)) for e in result["errors"]
                    ]
                    operation_match = re.search(
                        r"\b(?:query|mutation|subscription)\s+([_A-Za-z][_0-9A-Za-z]*)\b",
                        query,
                    )
                    operation = operation_name or (
                        operation_match.group(1) if operation_match else "anonymous"
                    )
                    logger.error(
                        "Protect GraphQL operation %s returned %d errors",
                        operation,
                        len(error_messages),
                    )
                    raise ProtectAPIError(
                        f"GraphQL error: {'; '.join(error_messages)}",
                        graphql_errors=result["errors"],
                    )

                return result.get("data", {})

            except httpx.HTTPStatusError as e:
                logger.error(
                    "Protect API request failed: %d",
                    e.response.status_code,
                )
                raise ProtectAPIError(
                    f"Protect API error: {e.response.status_code}",
                    status_code=e.response.status_code,
                ) from e
            except httpx.RequestError as e:
                logger.error("Protect request error: %s", type(e).__name__)
                raise ProtectAPIError(f"Request failed: {str(e)}") from e
