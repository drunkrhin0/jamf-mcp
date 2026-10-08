"""Verify production authentication requests with isolated HTTP transports."""

from urllib.parse import parse_qs

import httpx
import pytest

import jamf_mcp.auth as jamf_auth_module
import jamf_mcp.security_auth as security_auth_module
from jamf_mcp.auth import JamfAuth
from jamf_mcp.security_auth import JamfSecurityAuth


async def test_jamf_oauth_uses_v1_token_endpoint_and_caches_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Post OAuth credentials to the Jamf Pro v1 endpoint and cache its token."""
    monkeypatch.setattr(jamf_auth_module.time, "time", lambda: 1_000.0)
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"access_token": "pro-token", "expires_in": 300})

    auth = JamfAuth("https://pro.example.test/", "client-id", "client-secret")
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert await auth.get_token(client) == "pro-token"
        assert await auth.get_token(client) == "pro-token"

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == "/api/v1/oauth/token"
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    assert parse_qs(request.content.decode()) == {
        "grant_type": ["client_credentials"],
        "client_id": ["client-id"],
        "client_secret": ["client-secret"],
    }
    assert auth._token is not None
    assert auth._token.expires_at == 1_300.0


async def test_security_token_only_login_uses_900_second_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use the documented 15-minute default when login returns only a token."""
    monkeypatch.setattr(security_auth_module.time, "time", lambda: 2_000.0)
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"token": "risk-token"})

    auth = JamfSecurityAuth("https://security.example.test/", "app-id", "app-secret")
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert await auth.get_token(client) == "risk-token"

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == "/v1/login"
    assert request.headers["authorization"].startswith("Basic ")
    assert request.headers["accept"] == "application/json"
    assert auth._token is not None
    assert auth._token.expires_at == 2_900.0
