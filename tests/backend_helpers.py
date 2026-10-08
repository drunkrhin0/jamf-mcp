"""Shared helpers for offline tests of production MCP tools and API clients."""

from collections.abc import AsyncIterator, Callable
from unittest.mock import AsyncMock

import httpx
import pytest
from mcp.server import MCPServer

from jamf_mcp.auth import JamfAuth
from jamf_mcp.client import JamfClient
from jamf_mcp.protect_auth import ProtectAuth
from jamf_mcp.protect_client import ProtectClient
from jamf_mcp.security_auth import JamfSecurityAuth
from jamf_mcp.security_client import JamfSecurityClient
from jamf_mcp.tools import register_all_tools

ResponseHandler = Callable[[httpx.Request], httpx.Response]


def make_server() -> MCPServer:
    """Register the production tool catalogue for an in-process MCP call."""
    server = MCPServer("behavior-test")
    register_all_tools(server)
    return server


class MockedClients:
    """Create production API clients whose HTTP requests use MockTransport."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.monkeypatch = monkeypatch
        self.http_clients: list[httpx.AsyncClient] = []

    def jamf_pro(self, handler: ResponseHandler) -> JamfClient:
        """Create a Jamf Pro client with a fixed test token and mock transport."""
        auth = JamfAuth("https://pro.example.test", "test-id", "test-secret")
        self.monkeypatch.setattr(auth, "get_token", AsyncMock(return_value="pro-token"))
        client = JamfClient(auth)
        client._client = self._http_client(handler)
        return client

    def protect(self, handler: ResponseHandler) -> ProtectClient:
        """Create a Protect client with a fixed test token and mock transport."""
        auth = ProtectAuth("https://protect.example.test", "test-id", "test-password")
        self.monkeypatch.setattr(auth, "get_token", AsyncMock(return_value="protect-token"))
        client = ProtectClient(auth)
        client._client = self._http_client(handler)
        return client

    def security(self, handler: ResponseHandler) -> JamfSecurityClient:
        """Create a Security Cloud client with a fixed test token and mock transport."""
        auth = JamfSecurityAuth("https://security.example.test", "test-id", "test-secret")
        self.monkeypatch.setattr(auth, "get_token", AsyncMock(return_value="security-token"))
        client = JamfSecurityClient(auth)
        client._client = self._http_client(handler)
        return client

    def auth_backed_client(
        self,
        product: str,
        handler: ResponseHandler,
    ) -> JamfClient | ProtectClient | JamfSecurityClient:
        """Create a client that obtains its token through the mocked transport."""
        if product == "jamf_pro":
            auth = JamfAuth("https://pro.example.test", "test-id", "test-secret")
            client = JamfClient(auth)
        elif product == "jamf_protect":
            auth = ProtectAuth("https://protect.example.test", "test-id", "test-password")
            client = ProtectClient(auth)
        else:
            auth = JamfSecurityAuth("https://security.example.test", "test-id", "test-secret")
            client = JamfSecurityClient(auth)
        client._client = self._http_client(handler)
        return client

    def _http_client(self, handler: ResponseHandler) -> httpx.AsyncClient:
        """Build and track one isolated HTTPX mock transport."""
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.http_clients.append(client)
        return client

    async def close(self) -> None:
        """Close all underlying HTTP clients without making auth requests."""
        for client in self.http_clients:
            await client.aclose()


@pytest.fixture
async def mocked_clients(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[MockedClients]:
    """Supply API clients with no live network or credential dependency."""
    clients = MockedClients(monkeypatch)
    yield clients
    await clients.close()
