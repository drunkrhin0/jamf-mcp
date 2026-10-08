# Copyright 2026, Jamf Software LLC
"""Authentication module for Jamf Security Cloud API.

Uses HTTP Basic Auth to obtain a JWT token for the RISK API.
The module handles automatic token refresh when tokens expire.
"""

import base64
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class SecurityTokenInfo:
    """Stores JWT token information with expiration tracking."""
    access_token: str
    expires_at: float  # Unix timestamp
    token_type: str = "Bearer"

    @property
    def is_expired(self) -> bool:
        """Check if token is expired (with 60 second buffer)."""
        return time.time() >= (self.expires_at - 60)


class JamfSecurityAuthError(Exception):
    """Raised when Jamf Security Cloud authentication fails."""
    pass


class JamfSecurityAuth:
    """Handles HTTP Basic Auth to JWT authentication for Jamf Security Cloud.

    Automatically refreshes tokens when they expire.
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
    ):
        """Initialize authentication handler.

        Args:
            base_url: Jamf Security Cloud URL (e.g., https://radar.wandera.com)
            username: API username
            password: API password

        Raises:
            JamfSecurityAuthError: If credentials are not provided
        """
        self.base_url = base_url.rstrip("/")
        self._token: Optional[SecurityTokenInfo] = None

        if not username or not password:
            raise JamfSecurityAuthError(
                "Jamf Security Cloud credentials required. Provide username and password."
            )

        self._username = username
        self._password = password
        logger.info("Using Jamf Security Cloud HTTP Basic Auth authentication")

    @classmethod
    def from_env(cls) -> "JamfSecurityAuth":
        """Create JamfSecurityAuth instance from environment variables.

        Environment variables:
            JAMF_SECURITY_URL: Jamf Security Cloud URL (required)
            JAMF_SECURITY_APP_ID: API username (required)
            JAMF_SECURITY_APP_SECRET: API password (required)

        Returns:
            Configured JamfSecurityAuth instance

        Raises:
            JamfSecurityAuthError: If required environment variables are missing
        """
        base_url = os.environ.get("JAMF_SECURITY_URL")
        if not base_url:
            raise JamfSecurityAuthError("JAMF_SECURITY_URL environment variable is required")

        username = os.environ.get("JAMF_SECURITY_APP_ID")
        password = os.environ.get("JAMF_SECURITY_APP_SECRET")

        if not username or not password:
            raise JamfSecurityAuthError(
                "JAMF_SECURITY_APP_ID and JAMF_SECURITY_APP_SECRET environment variables are required"
            )

        return cls(
            base_url=base_url,
            username=username,
            password=password,
        )

    @classmethod
    def is_configured(cls) -> bool:
        """Check if Jamf Security Cloud credentials are configured.

        Returns:
            True if all required environment variables are set
        """
        return bool(
            os.environ.get("JAMF_SECURITY_URL") and
            os.environ.get("JAMF_SECURITY_APP_ID") and
            os.environ.get("JAMF_SECURITY_APP_SECRET")
        )

    async def get_token(self, client: httpx.AsyncClient) -> str:
        """Get a valid JWT token, refreshing if necessary.

        Args:
            client: HTTP client for making requests

        Returns:
            Valid JWT token string

        Raises:
            JamfSecurityAuthError: If token acquisition fails
        """
        if self._token is None or self._token.is_expired:
            await self._refresh_token(client)

        return self._token.access_token

    async def _refresh_token(self, client: httpx.AsyncClient) -> None:
        """Refresh the JWT token using HTTP Basic Auth.

        Args:
            client: HTTP client for making requests

        Raises:
            JamfSecurityAuthError: If token refresh fails
        """
        login_url = f"{self.base_url}/v1/login"

        # Create Basic Auth header
        credentials = f"{self._username}:{self._password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        try:
            response = await client.post(
                login_url,
                headers={
                    "Authorization": f"Basic {encoded_credentials}",
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()

            data = response.json()
            # The API returns the JWT token directly
            jwt_token = data.get("token") or data.get("access_token")

            if not jwt_token:
                raise JamfSecurityAuthError("No token in authentication response")

            # The RISK login response may contain only `token`; Jamf documents
            # a 15-minute lifetime for that response.
            expires_in = data.get("expires_in", 900)

            self._token = SecurityTokenInfo(
                access_token=jwt_token,
                expires_at=time.time() + expires_in,
                token_type="Bearer",
            )
            logger.debug("JWT token acquired, expires in %d seconds", expires_in)

        except httpx.HTTPStatusError as e:
            logger.error("JWT token request failed: HTTP %d", e.response.status_code)
            raise JamfSecurityAuthError(
                f"Jamf Security Cloud authentication failed: {e.response.status_code}"
            ) from None
        except Exception as e:
            logger.error("JWT token request error: %s", type(e).__name__)
            raise JamfSecurityAuthError(
                f"Jamf Security Cloud authentication error: {type(e).__name__}"
            ) from None

    def invalidate_token(self) -> None:
        """Clear the cached token."""
        self._token = None
        logger.debug("Token invalidated")
