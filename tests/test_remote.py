"""Offline coverage for remote OAuth verification and per-tool authorization."""

from __future__ import annotations

import base64
import json
import sys
import time
from collections.abc import Mapping
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.routes import build_resource_metadata_url
from mcp.server.context import ServerRequestContext
from mcp_types import CallToolResult, ToolAnnotations

import jamf_mcp.server as server_module
from jamf_mcp.remote import (
    ADMIN_SCOPE,
    ADMIN_TOOL_NAMES,
    AUDIENCE_ENV,
    BEARER_TOKENS_ENV,
    ISSUER_ENV,
    READ_SCOPE,
    REMOTE_AUTH_MODE_ENV,
    REMOTE_DISABLED_TOOL_NAMES,
    RESOURCE_ENV,
    WRITE_SCOPE,
    BearerAuthSettings,
    JwtJwksTokenVerifier,
    RemoteAuthConfig,
    RemoteAuthConfigurationError,
    RemoteScopeHTTPMiddleware,
    RemoteToolScopeMiddleware,
    StaticBearerTokenVerifier,
    build_remote_auth,
    build_remote_http_app,
    build_remote_tool_scope_map,
    get_remote_resource_url,
    remote_auth_mode_from_env,
    validate_remote_resource_url,
)

ISSUER = "https://login.example.test/tenant"
RESOURCE = "https://jamf.example.test/mcp"
KEY_ID = "offline-test-key"


def _int_to_base64url(number: int) -> str:
    length = (number.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(number.to_bytes(length, "big")).rstrip(b"=").decode()


@pytest.fixture
def rsa_fixture() -> tuple[bytes, bytes, dict[str, str]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    numbers = public_key.public_numbers()
    jwk = {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": KEY_ID,
        "n": _int_to_base64url(numbers.n),
        "e": _int_to_base64url(numbers.e),
    }
    return private_pem, public_pem, jwk


def _signed_token(
    private_key: bytes,
    *,
    issuer: str = ISSUER,
    audience: str = RESOURCE,
    expiry: int | None = None,
    scope: str = "jamf:read jamf:write",
) -> str:
    claims: dict[str, Any] = {
        "iss": issuer,
        "aud": audience,
        "sub": "remote-user-42",
        "client_id": "ops-console",
        "scope": scope,
        "exp": int(time.time()) + 300 if expiry is None else expiry,
    }
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": KEY_ID})


def _metadata_transport(jwk: Mapping[str, str]) -> httpx.MockTransport:
    metadata = {
        "issuer": ISSUER,
        "jwks_uri": f"{ISSUER}/keys",
        "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token",
    }

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/tenant/.well-known/openid-configuration":
            return httpx.Response(200, json=metadata, request=request)
        if request.url.path == "/tenant/keys":
            return httpx.Response(200, json={"keys": [jwk]}, request=request)
        return httpx.Response(404, json={"error": "not found"}, request=request)

    return httpx.MockTransport(respond)


def _config() -> RemoteAuthConfig:
    return RemoteAuthConfig(issuer_url=ISSUER, resource_url=RESOURCE, audience=RESOURCE)


def _bearer_env(
    tokens: list[dict[str, Any]], *, resource: str = RESOURCE
) -> dict[str, str]:
    return {
        REMOTE_AUTH_MODE_ENV: "bearer",
        RESOURCE_ENV: resource,
        BEARER_TOKENS_ENV: json.dumps(tokens),
    }


def _bearer_entry(
    *, identity: str = "ops-reader", token: str = "b" * 48, scopes: list[str] | None = None
) -> dict[str, Any]:
    return {
        "identity": identity,
        "token": token,
        "scopes": [READ_SCOPE] if scopes is None else scopes,
    }


@pytest.mark.asyncio
async def test_verifier_discovers_jwks_and_returns_verified_access_token(
    rsa_fixture: tuple[bytes, bytes, dict[str, str]],
) -> None:
    private_key, _public_key, jwk = rsa_fixture
    async with httpx.AsyncClient(transport=_metadata_transport(jwk)) as client:
        verifier = JwtJwksTokenVerifier(_config(), http_client=client)
        verified = await verifier.verify_token(_signed_token(private_key))

    assert verified is not None
    assert verified.client_id == "ops-console"
    assert verified.subject == "remote-user-42"
    assert verified.scopes == [READ_SCOPE, WRITE_SCOPE]
    assert verified.resource == RESOURCE
    assert verified.claims is not None
    assert verified.claims["iss"] == ISSUER


@pytest.mark.asyncio
async def test_verifier_rejects_missing_required_or_mismatched_jwt_claims(
    rsa_fixture: tuple[bytes, bytes, dict[str, str]],
) -> None:
    private_key, _public_key, jwk = rsa_fixture
    invalid_tokens = [
        jwt.encode(
            {"iss": ISSUER, "aud": RESOURCE, "sub": "caller"},
            private_key,
            algorithm="RS256",
            headers={"kid": KEY_ID},
        ),
        _signed_token(private_key, issuer="https://other.example.test"),
        _signed_token(private_key, audience="https://other.example.test"),
        _signed_token(private_key, expiry=int(time.time()) - 10),
    ]

    async with httpx.AsyncClient(transport=_metadata_transport(jwk)) as client:
        verifier = JwtJwksTokenVerifier(_config(), http_client=client)
        results = [await verifier.verify_token(token) for token in invalid_tokens]

    assert results == [None, None, None, None]


@pytest.mark.asyncio
async def test_verifier_rejects_invalid_signature_and_unknown_key(
    rsa_fixture: tuple[bytes, bytes, dict[str, str]],
) -> None:
    private_key, _public_key, jwk = rsa_fixture
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_private_key = other_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    wrong_signature = _signed_token(other_private_key)
    unknown_key = jwt.encode(
        {
            "iss": ISSUER,
            "aud": RESOURCE,
            "sub": "caller",
            "exp": int(time.time()) + 300,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "not-in-jwks"},
    )

    async with httpx.AsyncClient(transport=_metadata_transport(jwk)) as client:
        verifier = JwtJwksTokenVerifier(_config(), http_client=client)
        assert await verifier.verify_token(wrong_signature) is None
        assert await verifier.verify_token(unknown_key) is None


def test_remote_auth_requires_explicit_secure_issuer_and_resource() -> None:
    with pytest.raises(RemoteAuthConfigurationError, match=ISSUER_ENV):
        RemoteAuthConfig.from_env({})

    with pytest.raises(RemoteAuthConfigurationError, match="HTTPS"):
        RemoteAuthConfig.from_env({ISSUER_ENV: "http://issuer.example", RESOURCE_ENV: RESOURCE})

    config = RemoteAuthConfig.from_env({ISSUER_ENV: ISSUER, RESOURCE_ENV: RESOURCE})
    assert config.audience == RESOURCE
    custom_audience = RemoteAuthConfig.from_env(
        {ISSUER_ENV: ISSUER, RESOURCE_ENV: RESOURCE, AUDIENCE_ENV: "jamf-api-resource"}
    )
    assert custom_audience.audience == "jamf-api-resource"


def test_bearer_auth_config_fails_closed_without_leaking_configured_tokens() -> None:
    token = "secret-token-that-must-not-appear-in-errors-123"
    assert remote_auth_mode_from_env({}) == "oauth"

    auth, verifier = build_remote_auth(_bearer_env([_bearer_entry(token=token)]))
    assert isinstance(auth, BearerAuthSettings)
    assert auth.issuer_url is None
    assert auth.resource_server_url is None
    assert isinstance(verifier, StaticBearerTokenVerifier)
    assert verifier.resource_url == RESOURCE
    assert token not in repr(verifier)

    invalid_entries = [
        [],
        [_bearer_entry(token="short")],
        [_bearer_entry(token="bad-token-value-contains-space-and-enough-length ")],
        [_bearer_entry(token="é" * 40)],
        [_bearer_entry(token="x" * 20 + "\n" + "x" * 20)],
        [_bearer_entry(token=token, scopes=[READ_SCOPE, "jamf:unknown"])],
        [_bearer_entry(token=token, scopes=[WRITE_SCOPE])],
    ]
    for entries in invalid_entries:
        with pytest.raises(RemoteAuthConfigurationError) as error:
            build_remote_auth(_bearer_env(entries))
        assert token not in str(error.value)

    duplicate_identity = [
        _bearer_entry(identity="same", token="a" * 48),
        _bearer_entry(identity="same", token="b" * 48),
    ]
    duplicate_token = [
        _bearer_entry(identity="first", token="c" * 48),
        _bearer_entry(identity="second", token="c" * 48),
    ]
    for entries in (duplicate_identity, duplicate_token):
        with pytest.raises(RemoteAuthConfigurationError):
            build_remote_auth(_bearer_env(entries))

    with pytest.raises(RemoteAuthConfigurationError, match="JSON array"):
        build_remote_auth(
            {
                REMOTE_AUTH_MODE_ENV: "bearer",
                RESOURCE_ENV: RESOURCE,
                BEARER_TOKENS_ENV: "not-json",
            }
        )

    with pytest.raises(RemoteAuthConfigurationError, match=RESOURCE_ENV):
        build_remote_auth({REMOTE_AUTH_MODE_ENV: "bearer", BEARER_TOKENS_ENV: "[]"})
    with pytest.raises(RemoteAuthConfigurationError, match="HTTPS"):
        build_remote_auth(
            _bearer_env([_bearer_entry()], resource="http://jamf.example.test/mcp")
        )
    with pytest.raises(RemoteAuthConfigurationError, match=REMOTE_AUTH_MODE_ENV):
        build_remote_auth({REMOTE_AUTH_MODE_ENV: "disabled"})


@pytest.mark.parametrize(
    "resource",
    ["https://jamf.example.test:bad/mcp", "https://jamf.example.test:65536/mcp"],
)
def test_remote_resource_url_rejects_malformed_ports(resource: str) -> None:
    with pytest.raises(RemoteAuthConfigurationError, match="HTTPS"):
        validate_remote_resource_url(resource)


@pytest.mark.asyncio
async def test_bearer_verifier_returns_configured_writer_and_admin_scopes() -> None:
    reader_token = "r" * 48
    writer_token = "w" * 48
    admin_token = "a" * 48
    auth, verifier = build_remote_auth(
        _bearer_env(
            [
                _bearer_entry(identity="reader", token=reader_token),
                _bearer_entry(
                    identity="writer",
                    token=writer_token,
                    scopes=[READ_SCOPE, WRITE_SCOPE],
                ),
                _bearer_entry(
                    identity="admin",
                    token=admin_token,
                    scopes=[READ_SCOPE, WRITE_SCOPE, ADMIN_SCOPE],
                ),
            ]
        )
    )

    reader = await verifier.verify_token(reader_token)
    writer = await verifier.verify_token(writer_token)
    admin = await verifier.verify_token(admin_token)

    assert isinstance(auth, BearerAuthSettings)
    assert reader is not None and reader.scopes == [READ_SCOPE]
    assert writer is not None and set(writer.scopes) == {READ_SCOPE, WRITE_SCOPE}
    assert admin is not None and set(admin.scopes) == {READ_SCOPE, WRITE_SCOPE, ADMIN_SCOPE}
    assert writer.client_id == "writer"
    assert admin.client_id == "admin"


@pytest.mark.asyncio
async def test_sdk_settings_publish_unauthenticated_protected_resource_metadata() -> None:
    auth, verifier = build_remote_auth({ISSUER_ENV: ISSUER, RESOURCE_ENV: RESOURCE})
    server = MCPServer("remote-test", auth=auth, token_verifier=verifier)
    app = build_remote_http_app(server)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://jamf.example.test",
    ) as client:
        response = await client.get(str(build_resource_metadata_url(auth.resource_server_url)))

    assert str(auth.resource_server_url) == RESOURCE
    assert auth.validate_token_resource is True
    assert auth.required_scopes == [READ_SCOPE]
    assert response.status_code == 200
    assert response.json()["authorization_servers"] == [ISSUER]
    assert response.json()["scopes_supported"] == [READ_SCOPE]


@pytest.mark.asyncio
async def test_static_bearer_http_access_and_scope_denial_publish_no_oauth_metadata() -> None:
    read_token = "r" * 48
    auth, verifier = build_remote_auth(_bearer_env([_bearer_entry(token=read_token)]))
    scopes = {"read_tool": [READ_SCOPE], "write_tool": [READ_SCOPE, WRITE_SCOPE]}
    writes: list[bool] = []
    server = MCPServer(
        "static-bearer-test",
        auth=auth,
        token_verifier=verifier,
        middleware=[
            RemoteToolScopeMiddleware(
                scopes,
                advertise_security_schemes=False,
            )
        ],
    )

    @server.tool(
        name="read_tool",
        annotations=ToolAnnotations(read_only_hint=True),
        structured_output=False,
    )
    async def read_tool() -> str:
        return "read succeeded"

    @server.tool(
        name="write_tool",
        annotations=ToolAnnotations(read_only_hint=False),
        structured_output=False,
    )
    async def write_tool() -> str:
        writes.append(True)
        return "write happened"

    app = build_remote_http_app(
        server,
        tool_scopes=scopes,
        stateless_http=True,
        json_response=True,
    )
    routes = {getattr(route, "path", None) for route in app.routes}
    assert "/mcp" in routes
    assert not any("oauth-protected-resource" in (path or "") for path in routes)

    base_headers = {
        "Authorization": f"Bearer {read_token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://jamf.example.test",
    ) as client:
        async with app.router.lifespan_context(app):
            initialized = await client.post(
                "/mcp",
                headers=base_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "bearer-test", "version": "1.0"},
                    },
                },
            )
            listed = await client.post(
                "/mcp",
                headers=base_headers,
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            )
            read = await client.post(
                "/mcp",
                headers=base_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "read_tool", "arguments": {}},
                },
            )
            denied = await client.post(
                "/mcp",
                headers=base_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "write_tool", "arguments": {}},
                },
            )
            invalid = await client.post(
                "/mcp",
                headers={**base_headers, "Authorization": f"Bearer {'x' * 48}"},
                json={"jsonrpc": "2.0", "id": 5, "method": "tools/list", "params": {}},
            )

    assert initialized.status_code == 200
    assert listed.status_code == 200
    listed_tool = listed.json()["result"]["tools"][0]
    assert "securitySchemes" not in listed_tool
    assert "securitySchemes" not in listed_tool.get("_meta", {})
    assert read.status_code == 200
    assert read.json()["result"]["content"][0]["text"] == "read succeeded"
    assert denied.status_code == 403
    assert denied.json()["result"]["isError"] is True
    assert "_meta" not in denied.json()["result"]
    assert writes == []
    assert invalid.status_code == 401
    assert "resource_metadata" not in invalid.headers.get("www-authenticate", "")


def test_main_bearer_uses_public_resource_for_path_and_transport_security(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcp.server import transport_security
    from mcp.server.transport_security import TransportSecuritySettings as OriginalSettings

    resource = "https://jamf.example.test/api/mcp"
    auth, verifier = build_remote_auth(
        _bearer_env([_bearer_entry()], resource=resource)
    )
    server = MCPServer("main-bearer-test", auth=auth, token_verifier=verifier)
    monkeypatch.setattr(server_module, "create_server", lambda **_kwargs: server)
    monkeypatch.setattr(sys, "argv", ["jamf-mcp", "--transport", "streamable-http"])

    security_settings: dict[str, Any] = {}

    def capture_security_settings(**kwargs: Any) -> OriginalSettings:
        security_settings.update(kwargs)
        return OriginalSettings(**kwargs)

    monkeypatch.setattr(
        transport_security,
        "TransportSecuritySettings",
        capture_security_settings,
    )
    import uvicorn

    launched: dict[str, Any] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **_kwargs: launched.setdefault("app", app))

    server_module.main()

    app = launched["app"]
    assert get_remote_resource_url(server) == resource
    assert security_settings["allowed_hosts"] == [
        "jamf.example.test",
        "127.0.0.1:*",
        "localhost:*",
        "[::1]:*",
    ]
    assert security_settings["allowed_origins"] == ["https://jamf.example.test"]
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/api/mcp" in paths
    assert not any("oauth-protected-resource" in (path or "") for path in paths)


@pytest.mark.asyncio
async def test_remote_factory_modern_bearer_flow_lists_safe_tools_and_runs_setup_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "factory-reader-token-with-strong-length-123"
    monkeypatch.setenv(REMOTE_AUTH_MODE_ENV, "bearer")
    monkeypatch.setenv(RESOURCE_ENV, RESOURCE)
    monkeypatch.setenv(
        BEARER_TOKENS_ENV,
        json.dumps([_bearer_entry(identity="factory-reader", token=token)]),
    )
    server = server_module.create_server(remote=True)
    app = build_remote_http_app(server, stateless_http=True, json_response=True)
    routes = {getattr(route, "path", None) for route in app.routes}
    assert "/mcp" in routes
    assert not any("oauth-protected-resource" in (path or "") for path in routes)

    modern_meta = {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "factory-test", "version": "1.0"},
        "io.modelcontextprotocol/clientCapabilities": {},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2026-07-28",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://jamf.example.test",
    ) as client:
        async with app.router.lifespan_context(app):
            discovered = await client.post(
                "/mcp",
                headers={**headers, "Mcp-Method": "server/discover"},
                json={
                    "jsonrpc": "2.0",
                    "id": 10,
                    "method": "server/discover",
                    "params": {"_meta": modern_meta},
                },
            )
            listed = await client.post(
                "/mcp",
                headers={**headers, "Mcp-Method": "tools/list"},
                json={
                    "jsonrpc": "2.0",
                    "id": 11,
                    "method": "tools/list",
                    "params": {"_meta": modern_meta},
                },
            )
            setup_status = await client.post(
                "/mcp",
                headers={
                    **headers,
                    "Mcp-Method": "tools/call",
                    "Mcp-Name": "jamf_get_setup_status",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 12,
                    "method": "tools/call",
                    "params": {
                        "name": "jamf_get_setup_status",
                        "arguments": {},
                        "_meta": modern_meta,
                    },
                },
            )

    assert discovered.status_code == 200
    assert listed.status_code == 200
    tools = listed.json()["result"]["tools"]
    assert tools
    assert all("securitySchemes" not in tool for tool in tools)
    assert all("securitySchemes" not in tool.get("_meta", {}) for tool in tools)
    assert all(tool["name"] != "jamf_create_api_client_credentials" for tool in tools)
    assert setup_status.status_code == 200
    assert setup_status.json()["result"]["isError"] is False
    assert json.loads(setup_status.json()["result"]["content"][0]["text"])["success"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scopes", "tool_name", "is_allowed"),
    [
        ([READ_SCOPE], "jamf_get_computers", True),
        ([READ_SCOPE, WRITE_SCOPE], "jamf_update_computer", True),
        ([READ_SCOPE, WRITE_SCOPE], "jamf_create_api_role", False),
        ([READ_SCOPE, WRITE_SCOPE, ADMIN_SCOPE], "jamf_create_api_role", True),
    ],
)
async def test_tool_middleware_enforces_scopes_on_every_call(
    scopes: list[str], tool_name: str, is_allowed: bool
) -> None:
    middleware = RemoteToolScopeMiddleware(
        {
            "jamf_get_computers": [READ_SCOPE],
            "jamf_update_computer": [READ_SCOPE, WRITE_SCOPE],
            "jamf_create_api_role": [READ_SCOPE, WRITE_SCOPE, ADMIN_SCOPE],
        },
        resource_metadata_url=f"{RESOURCE}/.well-known/oauth-protected-resource",
    )
    access_token = AccessToken(token="verified", client_id="caller", scopes=scopes)
    context_token = auth_context_var.set(AuthenticatedUser(access_token))
    called = False

    async def call_next(_context: ServerRequestContext[Any, Any]) -> dict[str, bool]:
        nonlocal called
        called = True
        return {"called": True}

    try:
        context = ServerRequestContext(
            session=None,
            lifespan_context={},
            protocol_version="2025-11-25",
            method="tools/call",
            params={"name": tool_name},
        )
        result = await middleware(context, call_next)
    finally:
        auth_context_var.reset(context_token)

    assert called is is_allowed
    if not is_allowed:
        assert isinstance(result, CallToolResult)
        assert result.is_error is True
        assert result.meta is not None
        challenge = result.meta["mcp/www_authenticate"][0]
        assert 'error="insufficient_scope"' in challenge
        assert "error_description=" in challenge


@pytest.mark.asyncio
async def test_bearer_dispatch_scope_denial_has_no_oauth_link_metadata() -> None:
    access_token = AccessToken(
        token="verified",
        client_id="ops-reader",
        scopes=[READ_SCOPE],
        resource=RESOURCE,
    )
    context_token = auth_context_var.set(AuthenticatedUser(access_token))
    called = False

    async def call_next(_context: ServerRequestContext[Any, Any]) -> dict[str, bool]:
        nonlocal called
        called = True
        return {"called": True}

    try:
        middleware = RemoteToolScopeMiddleware(
            {"write_tool": [READ_SCOPE, WRITE_SCOPE]},
            resource_metadata_url=None,
            advertise_security_schemes=False,
        )
        context = ServerRequestContext(
            session=None,
            lifespan_context={},
            protocol_version="2025-11-25",
            method="tools/call",
            params={"name": "write_tool"},
        )
        result = await middleware(context, call_next)
    finally:
        auth_context_var.reset(context_token)

    assert called is False
    assert isinstance(result, CallToolResult)
    assert result.meta is None


def test_registry_annotations_drive_scopes_and_secret_tool_is_disabled_remotely() -> None:
    scopes = build_remote_tool_scope_map()

    assert scopes["jamf_get_computer"] == frozenset({READ_SCOPE})
    assert scopes["jamf_get_ddm_status"] == frozenset({READ_SCOPE})
    assert scopes["jamf_get_device_compliance_information"] == frozenset({READ_SCOPE})
    assert scopes["jamf_update_computer"] == frozenset({READ_SCOPE, WRITE_SCOPE})
    assert all(
        scopes[name] == frozenset({READ_SCOPE, WRITE_SCOPE, ADMIN_SCOPE})
        for name in ADMIN_TOOL_NAMES
        if name not in REMOTE_DISABLED_TOOL_NAMES
    )
    assert "jamf_create_api_client_credentials" in REMOTE_DISABLED_TOOL_NAMES
    assert "jamf_create_api_client_credentials" not in scopes


@pytest.mark.asyncio
async def test_http_app_returns_403_and_complete_bearer_challenge_for_insufficient_scope(
    rsa_fixture: tuple[bytes, bytes, dict[str, str]],
) -> None:
    private_key, _public_key, jwk = rsa_fixture
    config = _config()
    auth, _ = build_remote_auth({ISSUER_ENV: ISSUER, RESOURCE_ENV: RESOURCE})
    async with httpx.AsyncClient(transport=_metadata_transport(jwk)) as issuer_client:
        verifier = JwtJwksTokenVerifier(config, http_client=issuer_client)
        server = MCPServer("remote-scope-test", auth=auth, token_verifier=verifier)
        app = build_remote_http_app(
            server,
            tool_scopes={"write_tool": [READ_SCOPE, WRITE_SCOPE]},
            stateless_http=True,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="https://jamf.example.test",
        ) as client:
            unauthenticated = await client.post(
                "/mcp",
                headers={"Content-Type": "application/json"},
                json={"jsonrpc": "2.0", "id": 6, "method": "tools/list", "params": {}},
            )
            response = await client.post(
                "/mcp",
                headers={
                    "Authorization": f"Bearer {_signed_token(private_key, scope=READ_SCOPE)}",
                    "Content-Type": "application/json",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "tools/call",
                    "params": {"name": "write_tool", "arguments": {}},
                },
            )

    assert unauthenticated.status_code == 401
    assert 'scope="jamf:read"' in unauthenticated.headers["www-authenticate"]
    assert f'resource_metadata="{build_resource_metadata_url(auth.resource_server_url)}"' in (
        unauthenticated.headers["www-authenticate"]
    )
    assert response.status_code == 403
    challenge = response.headers["www-authenticate"]
    assert 'error="insufficient_scope"' in challenge
    assert 'scope="jamf:read jamf:write"' in challenge
    expected_metadata = (
        f'resource_metadata="{build_resource_metadata_url(auth.resource_server_url)}"'
    )
    assert expected_metadata in challenge
    rpc_error = response.json()
    assert rpc_error["jsonrpc"] == "2.0"
    assert rpc_error["id"] == 7
    assert rpc_error["result"]["isError"] is True
    assert rpc_error["result"]["resultType"] == "complete"
    assert 'error="insufficient_scope"' in rpc_error["result"]["_meta"]["mcp/www_authenticate"][0]


@pytest.mark.asyncio
async def test_http_app_preserves_body_and_emits_tool_security_schemes_and_allowed_call(
    rsa_fixture: tuple[bytes, bytes, dict[str, str]],
) -> None:
    private_key, _public_key, jwk = rsa_fixture
    config = _config()
    auth, _ = build_remote_auth({ISSUER_ENV: ISSUER, RESOURCE_ENV: RESOURCE})
    scope_map = {"read_tool": [READ_SCOPE]}
    async with httpx.AsyncClient(transport=_metadata_transport(jwk)) as issuer_client:
        verifier = JwtJwksTokenVerifier(config, http_client=issuer_client)
        server = MCPServer(
            "remote-allowed-test",
            auth=auth,
            token_verifier=verifier,
            middleware=[
                RemoteToolScopeMiddleware(
                    scope_map,
                    resource_metadata_url=str(build_resource_metadata_url(auth.resource_server_url)),
                )
            ],
        )

        @server.tool(
            name="read_tool",
            annotations=ToolAnnotations(read_only_hint=True),
            meta={"securitySchemes": [{"type": "oauth2", "scopes": [READ_SCOPE]}]},
            structured_output=False,
        )
        async def read_tool() -> str:
            return "read succeeded"

        app = build_remote_http_app(
            server,
            tool_scopes=scope_map,
            stateless_http=True,
            json_response=True,
        )
        bearer = f"Bearer {_signed_token(private_key, scope=READ_SCOPE)}"
        headers = {
            "Authorization": bearer,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="https://jamf.example.test",
        ) as client:
            async with app.router.lifespan_context(app):
                initialized = await client.post(
                    "/mcp",
                    headers=headers,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-11-25",
                            "capabilities": {},
                            "clientInfo": {"name": "remote-test", "version": "1.0"},
                        },
                    },
                )
                tools_list = await client.post(
                    "/mcp",
                    headers=headers,
                    json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                )
                called = await client.post(
                    "/mcp",
                    headers=headers,
                    json={
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {"name": "read_tool", "arguments": {}},
                    },
                )
                unknown = await client.post(
                    "/mcp",
                    headers=headers,
                    json={
                        "jsonrpc": "2.0",
                        "id": 4,
                        "method": "tools/call",
                        "params": {"name": "unknown_tool", "arguments": {}},
                    },
                )
                malformed = await client.post(
                    "/mcp",
                    headers=headers,
                    json={"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {}},
                )

    assert initialized.status_code == 200
    assert tools_list.status_code == 200
    listed = tools_list.json()["result"]["tools"][0]
    schemes = [{"type": "oauth2", "scopes": [READ_SCOPE]}]
    assert listed["securitySchemes"] == schemes
    assert listed["_meta"]["securitySchemes"] == schemes
    assert called.status_code == 200
    assert called.json()["result"]["content"][0]["text"] == "read succeeded"
    assert unknown.status_code == 200
    assert unknown.json()["id"] == 4
    assert unknown.json()["error"]["code"] == -32602
    assert malformed.status_code == 200
    assert malformed.json()["error"]["code"] == -32602
    assert malformed.json()["id"] == 5


@pytest.mark.asyncio
async def test_modern_http_protocol_discover_list_call_and_scope_step_up(
    rsa_fixture: tuple[bytes, bytes, dict[str, str]],
) -> None:
    private_key, _public_key, jwk = rsa_fixture
    auth, _ = build_remote_auth({ISSUER_ENV: ISSUER, RESOURCE_ENV: RESOURCE})
    scope_map = {
        "read_tool": [READ_SCOPE],
        "write_tool": [READ_SCOPE, WRITE_SCOPE],
    }
    async with httpx.AsyncClient(transport=_metadata_transport(jwk)) as issuer_client:
        verifier = JwtJwksTokenVerifier(_config(), http_client=issuer_client)
        server = MCPServer(
            "remote-modern-test",
            auth=auth,
            token_verifier=verifier,
            middleware=[RemoteToolScopeMiddleware(scope_map)],
        )

        @server.tool(name="read_tool", structured_output=False)
        async def read_tool() -> str:
            return "modern read succeeded"

        @server.tool(name="write_tool", structured_output=False)
        async def write_tool() -> str:
            return "write should be denied before dispatch"

        app = build_remote_http_app(
            server,
            tool_scopes=scope_map,
            stateless_http=True,
            json_response=True,
        )
        headers = {
            "Authorization": f"Bearer {_signed_token(private_key, scope=READ_SCOPE)}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2026-07-28",
        }
        modern_meta = {
            "io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientInfo": {"name": "remote-test", "version": "1.0"},
            "io.modelcontextprotocol/clientCapabilities": {},
        }

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="https://jamf.example.test",
        ) as client:
            async with app.router.lifespan_context(app):
                discovered = await client.post(
                    "/mcp",
                    headers={**headers, "Mcp-Method": "server/discover"},
                    json={
                        "jsonrpc": "2.0",
                        "id": 10,
                        "method": "server/discover",
                        "params": {"_meta": modern_meta},
                    },
                )
                listed = await client.post(
                    "/mcp",
                    headers={**headers, "Mcp-Method": "tools/list"},
                    json={
                        "jsonrpc": "2.0",
                        "id": 11,
                        "method": "tools/list",
                        "params": {"_meta": modern_meta},
                    },
                )
                called = await client.post(
                    "/mcp",
                    headers={**headers, "Mcp-Method": "tools/call", "Mcp-Name": "read_tool"},
                    json={
                        "jsonrpc": "2.0",
                        "id": 12,
                        "method": "tools/call",
                        "params": {"name": "read_tool", "arguments": {}, "_meta": modern_meta},
                    },
                )
                denied = await client.post(
                    "/mcp",
                    headers={**headers, "Mcp-Method": "tools/call", "Mcp-Name": "write_tool"},
                    json={
                        "jsonrpc": "2.0",
                        "id": 13,
                        "method": "tools/call",
                        "params": {"name": "write_tool", "arguments": {}, "_meta": modern_meta},
                    },
                )

    assert discovered.status_code == 200
    assert "2026-07-28" in discovered.json()["result"]["supportedVersions"]
    assert listed.status_code == 200
    assert listed.json()["result"]["tools"][0]["securitySchemes"] == [
        {"type": "oauth2", "scopes": [READ_SCOPE]}
    ]
    assert called.status_code == 200
    assert called.json()["result"]["content"][0]["text"] == "modern read succeeded"
    assert denied.status_code == 403
    assert denied.json()["id"] == 13
    assert denied.json()["result"]["isError"] is True
    assert 'scope="jamf:read jamf:write"' in denied.headers["www-authenticate"]


@pytest.mark.asyncio
async def test_http_body_limit_rejects_oversized_chunk_without_forwarding() -> None:
    forwarded = False
    response_messages: list[dict[str, Any]] = []

    async def app(_scope: dict[str, Any], _receive: Any, _send: Any) -> None:
        nonlocal forwarded
        forwarded = True

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"x" * 100_000, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        response_messages.append(message)

    middleware = RemoteScopeHTTPMiddleware(
        app,
        tool_scopes={},
        resource_metadata_url=f"{RESOURCE}/.well-known/oauth-protected-resource",
        mcp_path="/mcp",
        max_body_bytes=8,
    )
    token = AccessToken(token="verified", client_id="caller", scopes=[READ_SCOPE])
    scope = {
        "type": "http",
        "path": "/mcp",
        "method": "POST",
        "user": AuthenticatedUser(token),
    }

    await middleware(scope, receive, send)

    assert not forwarded
    assert response_messages[0]["status"] == 413


@pytest.mark.asyncio
async def test_remote_http_app_uses_public_resource_path() -> None:
    resource = "https://jamf.example.test/api/mcp"
    auth, verifier = build_remote_auth(
        {ISSUER_ENV: ISSUER, RESOURCE_ENV: resource}
    )
    server = MCPServer("remote-path-test", auth=auth, token_verifier=verifier)
    app = build_remote_http_app(server)

    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/api/mcp" in paths
    assert "/.well-known/oauth-protected-resource/api/mcp" in paths

    with pytest.raises(RemoteAuthConfigurationError, match="must match"):
        build_remote_http_app(server, streamable_http_path="/mcp")
