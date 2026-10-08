# Copyright 2026, Jamf Software LLC
"""Authentication module for Jamf Protect API.

Uses client credentials (client_id + password) for authentication.
The module handles automatic token refresh when tokens expire.
"""

import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ProtectTokenInfo:
    """Stores Protect token information with expiration tracking."""
    access_token: str
    expires_at: float  # Unix timestamp
    token_type: str = "Bearer"

    @property
    def is_expired(self) -> bool:
        """Check if token is expired (with 60 second buffer)."""
        return time.time() >= (self.expires_at - 60)


class ProtectAuthError(Exception):
    """Raised when Protect authentication fails."""
    pass


class ProtectAuth:
    """Handles authentication for Jamf Protect API.

    Uses client_id and password to obtain access tokens.
    Automatically refreshes tokens when they expire.
    """

    def __init__(
        self,
        base_url: str,
        client_id: str,
        password: str,
    ):
        """Initialize authentication handler.

        Args:
            base_url: Jamf Protect URL (e.g., https://tenant.protect.jamfcloud.com)
            client_id: API client ID
            password: API client password

        Raises:
            ProtectAuthError: If credentials are not provided
        """
        self.base_url = base_url.rstrip("/")
        self._token: Optional[ProtectTokenInfo] = None

        if not client_id or not password:
            raise ProtectAuthError(
                "Protect credentials required. Provide client_id and password."
            )

        self._client_id = client_id
        self._password = password
        logger.info("Jamf Protect authentication configured")

    @classmethod
    def from_env(cls) -> Optional["ProtectAuth"]:
        """Create ProtectAuth instance from environment variables.

        Environment variables:
            JAMF_PROTECT_URL: Jamf Protect URL (required)
            JAMF_PROTECT_CLIENT_ID: API client ID (required)
            JAMF_PROTECT_PASSWORD: API client password (required)

        Returns:
            Configured ProtectAuth instance, or None if not configured
        """
        base_url = os.environ.get("JAMF_PROTECT_URL")
        client_id = os.environ.get("JAMF_PROTECT_CLIENT_ID")
        password = os.environ.get("JAMF_PROTECT_PASSWORD")

        # If any required env var is missing, return None (not configured)
        if not base_url or not client_id or not password:
            return None

        return cls(
            base_url=base_url,
            client_id=client_id,
            password=password,
        )

    async def get_token(self, client: httpx.AsyncClient) -> str:
        """Get a valid access token, refreshing if necessary.

        Args:
            client: HTTP client for making requests

        Returns:
            Valid access token string

        Raises:
            ProtectAuthError: If token acquisition fails
        """
        if self._token is None or self._token.is_expired:
            await self._refresh_token(client)

        return self._token.access_token

    async def _refresh_token(self, client: httpx.AsyncClient) -> None:
        """Refresh the access token using client credentials.

        Args:
            client: HTTP client for making requests

        Raises:
            ProtectAuthError: If token refresh fails
        """
        token_url = f"{self.base_url}/token"

        try:
            response = await client.post(
                token_url,
                json={
                    "client_id": self._client_id,
                    "password": self._password,
                },
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

            data = response.json()
            # Protect API returns access_token and expires_in
            expires_in = data.get("expires_in", 3600)  # Default 1 hour

            self._token = ProtectTokenInfo(
                access_token=data["access_token"],
                expires_at=time.time() + expires_in,
                token_type=data.get("token_type", "Bearer"),
            )
            logger.debug("Protect token acquired, expires in %d seconds", expires_in)

        except httpx.HTTPStatusError as e:
            logger.error("Protect token request failed: HTTP %d", e.response.status_code)
            raise ProtectAuthError(
                f"Protect authentication failed: {e.response.status_code}"
            ) from None
        except KeyError as e:
            logger.error("Protect token response missing field: %s", str(e))
            raise ProtectAuthError(f"Invalid token response: missing {e}") from e
        except Exception as e:
            logger.error("Protect token request error: %s", type(e).__name__)
            raise ProtectAuthError(
                f"Protect authentication error: {type(e).__name__}"
            ) from None

    def invalidate_token(self) -> None:
        """Clear the current token."""
        self._token = None
