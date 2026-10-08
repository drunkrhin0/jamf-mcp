# Copyright 2026, Jamf Software LLC
"""Jamf Security Cloud API Client.

Provides an interface for the Jamf RISK API endpoints.
Handles authentication and request formatting.
"""

import logging
from contextlib import asynccontextmanager
from typing import Any, Optional
from urllib.parse import urljoin

import httpx

from .security_auth import JamfSecurityAuth, JamfSecurityAuthError

logger = logging.getLogger(__name__)


class JamfSecurityAPIError(Exception):
    """Raised when a Jamf Security Cloud API request fails."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class JamfSecurityClient:
    """Client for interacting with Jamf Security Cloud RISK API.

    Provides methods for retrieving device risk status and overriding risk levels.
    """

    # Default timeout for API requests (in seconds)
    DEFAULT_TIMEOUT = 30.0

    def __init__(self, auth: JamfSecurityAuth, timeout: float = DEFAULT_TIMEOUT):
        """Initialize Jamf Security Cloud client.

        Args:
            auth: JamfSecurityAuth instance for handling authentication
            timeout: Request timeout in seconds
        """
        self.auth = auth
        self.base_url = auth.base_url
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    @classmethod
    def from_env(cls, timeout: float = DEFAULT_TIMEOUT) -> "JamfSecurityClient":
        """Create JamfSecurityClient from environment variables.

        Args:
            timeout: Request timeout in seconds

        Returns:
            Configured JamfSecurityClient instance
        """
        auth = JamfSecurityAuth.from_env()
        return cls(auth=auth, timeout=timeout)

    @asynccontextmanager
    async def _get_client(self):
        """Get or create HTTP client as async context manager.

        Yields:
            httpx.AsyncClient instance
        """
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)

        try:
            yield self._client
        except Exception:
            raise

    async def close(self):
        """Close the HTTP client and invalidate token."""
        if self._client:
            self.auth.invalidate_token()
            await self._client.aclose()
            self._client = None

    async def _get_headers(self, client: httpx.AsyncClient) -> dict:
        """Get request headers with authentication.

        Args:
            client: HTTP client for token requests

        Returns:
            Dict of headers including Authorization
        """
        token = await self.auth.get_token(client)
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> Any:
        """Make an authenticated request to the Jamf Security Cloud API.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE)
            endpoint: API endpoint path (e.g., /risk/v1/devices)
            data: Request body data (for POST, PUT, PATCH)
            params: Query parameters

        Returns:
            Parsed JSON response

        Raises:
            JamfSecurityAPIError: If the request fails
        """
        url = urljoin(self.base_url, endpoint)

        async with self._get_client() as client:
            headers = await self._get_headers(client)

            try:
                response = await client.request(
                    method=method,
                    url=url,
                    json=data if data else None,
                    params=params,
                    headers=headers,
                )

                # Log request details for debugging
                logger.debug(
                    "%s %s -> %d",
                    method,
                    endpoint,
                    response.status_code,
                )

                response.raise_for_status()

                # Parse JSON response
                if response.text:
                    return response.json()
                return {}

            except httpx.HTTPStatusError as e:
                logger.error(
                    "Security API request failed: %s %s -> %d",
                    method,
                    endpoint,
                    e.response.status_code,
                )
                error_body = e.response.text
                raise JamfSecurityAPIError(
                    f"Jamf Security Cloud API error: {e.response.status_code}",
                    status_code=e.response.status_code,
                    response_body=error_body,
                ) from e
            except httpx.RequestError as e:
                logger.error("Request error: %s", type(e).__name__)
                raise JamfSecurityAPIError(f"Request failed: {str(e)}") from e

    # ==========================================================================
    # RISK API v1 Methods
    # ==========================================================================

    async def get_risk_devices_v1(
        self,
        page: int = 0,
        page_size: int = 100,
    ) -> dict:
        """Get device risk status using RISK API v1.

        This endpoint returns paginated device risk data.

        Args:
            page: Page number for pagination (0-indexed)
            page_size: Number of results per page (default: 100)

        Returns:
            Dict containing device risk information with pagination
        """
        params = {"page": page, "pageSize": page_size}
        return await self._request("GET", "/risk/v1/devices", params=params)

    # ==========================================================================
    # RISK API v2 Methods
    # ==========================================================================

    async def get_risk_devices_v2(self, page: int = 0, page_size: int = 100) -> dict:
        """Get device risk status using RISK API v2.

        This endpoint returns paginated device risk data.

        Args:
            page: Page number for pagination (0-indexed).
            page_size: Number of records per page (maximum 100).

        Returns:
            Dict containing device risk information
        """
        return await self._request(
            "GET", "/risk/v2/devices", params={"page": page, "pageSize": page_size}
        )

    # ==========================================================================
    # Risk Override Methods
    # ==========================================================================

    async def override_device_risk(
        self,
        device_ids: list[str],
        risk: str,
        source: str = "MANUAL",
    ) -> dict:
        """Override the risk level for specified devices.

        Args:
            device_ids: List of device IDs to override
            risk: New risk level (e.g., "LOW", "MEDIUM", "HIGH", "SEVERE")
            source: Source identifier for the override. Valid values: "MANUAL", "WANDERA"

        Returns:
            Dict containing the override result
        """
        data = {
            "deviceIds": device_ids,
            "risk": risk,
            "source": source,
        }
        return await self._request("PUT", "/risk/v1/override", data=data)
