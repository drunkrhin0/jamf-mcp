# Copyright 2026, Jamf Software LLC
"""Authentication module for Jamf Pro API.

Uses OAuth Client Credentials flow for authentication.
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
class TokenInfo:
    """Stores token information with expiration tracking."""
    access_token: str
    expires_at: float  # Unix timestamp
    token_type: str = "Bearer"

    @property
    def is_expired(self) -> bool:
        """Check if token is expired (with 60 second buffer)."""
        return time.time() >= (self.expires_at - 60)


class JamfAuthError(Exception):
    """Raised when authentication fails."""
    pass


class JamfAuth:
    """Handles OAuth client credentials authentication for Jamf Pro API.

    Automatically refreshes tokens when they expire.
    """

    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
    ):
        """Initialize authentication handler.

        Args:
            base_url: Jamf Pro instance URL (e.g., https://instance.jamfcloud.com)
            client_id: OAuth client ID
            client_secret: OAuth client secret

        Raises:
            JamfAuthError: If credentials are not provided
        """
        self.base_url = base_url.rstrip("/")
        self._token: Optional[TokenInfo] = None

        if not client_id or not client_secret:
            raise JamfAuthError(
                "OAuth credentials required. Provide client_id and client_secret."
            )

        self._client_id = client_id
        self._client_secret = client_secret
        logger.info("Using OAuth client credentials authentication")

    @classmethod
    def from_env(cls) -> "JamfAuth":
        """Create JamfAuth instance from environment variables.

        Environment variables:
            JAMF_PRO_URL: Jamf Pro instance URL (required)
            JAMF_PRO_CLIENT_ID: OAuth client ID (required)
            JAMF_PRO_CLIENT_SECRET: OAuth client secret (required)

        Returns:
            Configured JamfAuth instance

        Raises:
            JamfAuthError: If required environment variables are missing
        """
        base_url = os.environ.get("JAMF_PRO_URL")
        if not base_url:
            raise JamfAuthError("JAMF_PRO_URL environment variable is required")

        client_id = os.environ.get("JAMF_PRO_CLIENT_ID")
        client_secret = os.environ.get("JAMF_PRO_CLIENT_SECRET")

        if not client_id or not client_secret:
            raise JamfAuthError(
                "JAMF_PRO_CLIENT_ID and JAMF_PRO_CLIENT_SECRET environment variables are required"
            )

        return cls(
            base_url=base_url,
            client_id=client_id,
            client_secret=client_secret,
        )

    async def get_token(self, client: httpx.AsyncClient) -> str:
        """Get a valid access token, refreshing if necessary.

        Args:
            client: HTTP client for making requests

        Returns:
            Valid access token string

        Raises:
            JamfAuthError: If token acquisition fails
        """
        if self._token is None or self._token.is_expired:
            await self._refresh_token(client)

        return self._token.access_token

    async def _refresh_token(self, client: httpx.AsyncClient) -> None:
        """Refresh the access token using OAuth client credentials.

        Args:
            client: HTTP client for making requests

        Raises:
            JamfAuthError: If token refresh fails
        """
        token_url = f"{self.base_url}/api/v1/oauth/token"

        try:
            response = await client.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()

            data = response.json()
            expires_in = data.get("expires_in", 300)  # Default 5 minutes

            self._token = TokenInfo(
                access_token=data["access_token"],
                expires_at=time.time() + expires_in,
                token_type=data.get("token_type", "Bearer"),
            )
            logger.debug("OAuth token acquired, expires in %d seconds", expires_in)

        except httpx.HTTPStatusError as e:
            logger.error("OAuth token request failed: HTTP %d", e.response.status_code)
            raise JamfAuthError(f"OAuth authentication failed: {e.response.status_code}") from None
        except Exception as e:
            logger.error("OAuth token request error: %s", type(e).__name__)
            raise JamfAuthError(
                f"OAuth authentication error: {type(e).__name__}"
            ) from None

    async def invalidate_token(self, client: httpx.AsyncClient) -> None:
        """Invalidate the current token.

        Calls the token invalidation endpoint and clears local token.

        Args:
            client: HTTP client for making requests
        """
        if self._token is None:
            return

        try:
            await client.post(
                f"{self.base_url}/api/v1/auth/invalidate-token",
                headers={"Authorization": f"Bearer {self._token.access_token}"},
            )
            logger.debug("Token invalidated successfully")
        except Exception as e:
            logger.warning("Token invalidation failed: %s", type(e).__name__)
        finally:
            self._token = None
