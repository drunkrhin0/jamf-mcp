"""Read-only Jamf Platform gateway access with environment-scoped authentication."""

import asyncio
import os
import time
from typing import Any
from uuid import UUID

import httpx

from .client import JamfAPIError

PLATFORM_ENV_VARS = (
    "JAMF_PLATFORM_URL",
    "JAMF_PLATFORM_ENVIRONMENT_ID",
    "JAMF_PLATFORM_CLIENT_ID",
    "JAMF_PLATFORM_CLIENT_SECRET",
)
PLATFORM_URLS = frozenset(f"https://{region}.api.jamfcloud.com" for region in ("us", "eu", "apac"))


class PlatformClient:
    """Obtain cached gateway tokens and perform only environment-scoped GET requests."""

    def __init__(
        self,
        base_url: str,
        environment_id: str,
        client_id: str,
        client_secret: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        if self.base_url not in PLATFORM_URLS:
            raise ValueError(
                "JAMF_PLATFORM_URL must be an official regional HTTPS gateway base URL"
            )
        self.environment_id = str(UUID(environment_id))
        if not client_id or not client_secret:
            raise ValueError("Jamf Platform client ID and secret are required")
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = httpx.AsyncClient(timeout=30, transport=transport, follow_redirects=False)
        self._token: str | None = None
        self._expires_at = 0.0
        self._token_lock = asyncio.Lock()

    @classmethod
    def is_configured(cls) -> bool:
        """Return whether all required settings are supplied, without exposing values."""
        return all(os.environ.get(name) for name in PLATFORM_ENV_VARS)

    @classmethod
    def from_env(cls) -> "PlatformClient":
        """Build a gateway client from its separate Platform integration settings."""
        return cls(*(os.environ.get(name, "") for name in PLATFORM_ENV_VARS))

    async def close(self) -> None:
        """Release the HTTP connection pool and discard the cached token."""
        self._token = None
        await self._http.aclose()

    async def _access_token(self) -> str:
        async with self._token_lock:
            if self._token and time.monotonic() < self._expires_at:
                return self._token
            response = await self._http.post(
                f"{self.base_url}/auth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            if response.status_code != 200:
                raise JamfAPIError("Jamf Platform authentication failed", response.status_code)
            try:
                data = response.json()
                token = data["access_token"]
                lifetime = float(data["expires_in"])
                if not isinstance(token, str) or not token or not 0 < lifetime <= 86400:
                    raise ValueError
            except (KeyError, TypeError, ValueError) as error:
                raise JamfAPIError("Invalid Jamf Platform token response") from error
            self._token = token
            self._expires_at = time.monotonic() + lifetime - min(30, lifetime / 2)
            return token

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Read a fixed gateway resource; never accept an absolute URL or follow redirects."""
        if not path.startswith("/") or path.startswith("//") or "?" in path or "#" in path:
            raise ValueError("Platform resource must be a relative API path")
        try:
            for attempt in range(2):
                token = await self._access_token()
                response = await self._http.get(
                    f"{self.base_url}{path}",
                    params=params,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-Environment-Id": self.environment_id,
                        "Accept": "application/json",
                    },
                )
                if response.status_code == 401 and attempt == 0:
                    self._token = None
                    continue
                if not response.is_success:
                    raise JamfAPIError("Jamf Platform read failed", response.status_code)
                try:
                    return response.json()
                except ValueError as error:
                    raise JamfAPIError("Invalid JSON in Jamf Platform response") from error
        except httpx.HTTPError as error:
            raise JamfAPIError("Jamf Platform connection failed") from error
