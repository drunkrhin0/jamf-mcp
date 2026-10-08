"""Verify the deployment probe uses read-only requests and avoids secret output."""

import importlib.util
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from jamf_mcp.remote import RemoteAuthConfig

probe_spec = importlib.util.spec_from_file_location(
    "deployment_probe", Path(__file__).resolve().parents[1] / "scripts" / "validate_remote.py"
)
assert probe_spec is not None and probe_spec.loader is not None
probe = importlib.util.module_from_spec(probe_spec)
probe_spec.loader.exec_module(probe)

RESOURCE = "https://mcp.example.test/mcp"
ISSUER = "https://identity.example.test"


@pytest.mark.parametrize("token", [None, "secret-access-token"])
async def test_probe_checks_only_read_operations(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], token: str | None
) -> None:
    """Probe discovery/admission and optional MCP reads without disclosing bodies."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "resource": RESOURCE,
                    "authorization_servers": [ISSUER],
                    "scopes_supported": ["jamf:read"],
                },
            )
        if "authorization" not in request.headers:
            return httpx.Response(401, headers={"www-authenticate": 'Bearer scope="jamf:read"'})
        payload = json.loads(request.content)
        result: dict[str, Any] = {"resultType": "complete"}
        if payload["method"] == "server/discover":
            result["supportedVersions"] = ["2026-07-28"]
        elif payload["method"] == "tools/list":
            result["tools"] = [
                {
                    "name": "jamf_get_setup_status",
                    "securitySchemes": [{"type": "oauth2", "scopes": ["jamf:read"]}],
                }
            ]
        elif payload["method"] == "tools/call":
            assert payload["params"]["name"] == "jamf_get_setup_status"
            result["structuredContent"] = {"success": True, "private": "tenant-data-not-for-output"}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": result})

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(probe.httpx, "AsyncClient", lambda **kwargs: client)
    await probe.validate(RemoteAuthConfig(ISSUER, RESOURCE, RESOURCE), token)
    output = capsys.readouterr().out
    assert "PASS protected-resource discovery" in output
    assert "secret-access-token" not in output
    assert "tenant-data-not-for-output" not in output
    assert len(requests) == (2 if token is None else 5)


async def test_probe_rejects_incorrect_resource_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    """An endpoint advertising a different resource must fail before authenticated calls."""
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"resource": "https://wrong.example.test/mcp"})
        )
    )
    monkeypatch.setattr(probe.httpx, "AsyncClient", lambda **kwargs: client)
    with pytest.raises(ValueError, match="does not identify"):
        await probe.validate(RemoteAuthConfig(ISSUER, RESOURCE, RESOURCE), "secret-access-token")


@pytest.mark.parametrize("structured", [None, {}, {"success": False}])
async def test_probe_rejects_unsuccessful_setup_result(
    monkeypatch: pytest.MonkeyPatch, structured: dict[str, Any] | None
) -> None:
    """HTTP 200 alone must not make a missing/failed setup result pass."""

    def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "resource": RESOURCE,
                    "authorization_servers": [ISSUER],
                    "scopes_supported": ["jamf:read"],
                },
            )
        if "authorization" not in request.headers:
            return httpx.Response(401, headers={"www-authenticate": 'Bearer scope="jamf:read"'})
        payload = json.loads(request.content)
        result: dict[str, Any] = {"resultType": "complete"}
        if payload["method"] == "server/discover":
            result["supportedVersions"] = ["2026-07-28"]
        elif payload["method"] == "tools/list":
            result["tools"] = [
                {
                    "name": "jamf_get_setup_status",
                    "securitySchemes": [{"type": "oauth2", "scopes": ["jamf:read"]}],
                }
            ]
        elif structured is not None:
            result["structuredContent"] = structured
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": result})

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(probe.httpx, "AsyncClient", lambda **kwargs: client)
    with pytest.raises(ValueError, match="successful structured result"):
        await probe.validate(RemoteAuthConfig(ISSUER, RESOURCE, RESOURCE), "secret-access-token")


async def test_bearer_probe_checks_reads_without_oauth_discovery(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Gateway probes require no issuer, server token records or OAuth catalogue."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST"
        if "authorization" not in request.headers:
            return httpx.Response(401, headers={"www-authenticate": 'Bearer scope="jamf:read"'})
        payload = json.loads(request.content)
        result: dict[str, Any] = {"resultType": "complete"}
        if payload["method"] == "server/discover":
            result["supportedVersions"] = ["2026-07-28"]
        elif payload["method"] == "tools/list":
            result["tools"] = [{"name": "jamf_get_setup_status"}]
        else:
            assert payload["params"]["name"] == "jamf_get_setup_status"
            result["structuredContent"] = {"success": True, "private": "private-body"}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": result})

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(probe.httpx, "AsyncClient", lambda **kwargs: client)
    await probe.validate(probe.BearerProbeConfig(RESOURCE), "gateway-probe-secret")
    assert len(requests) == 4
    output = capsys.readouterr().out
    assert "gateway validation" in output
    assert "OAuth linking" not in output
    assert "gateway-probe-secret" not in output
    assert "private-body" not in output


@pytest.mark.parametrize("auth_mode", ["oauth", "bearer"])
@pytest.mark.parametrize("failure", [None, "isError", "unsuccessful"])
async def test_selected_backend_reads_go_through_mcp(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    auth_mode: str,
    failure: str | None,
) -> None:
    """Selected products use fixed reads; backend failures and private data stay private."""
    tool_calls: list[dict[str, Any]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={
                "resource": RESOURCE,
                "authorization_servers": [ISSUER],
                "scopes_supported": ["jamf:read"],
            })
        if "authorization" not in request.headers:
            return httpx.Response(401, headers={"www-authenticate": 'Bearer scope="jamf:read"'})
        payload = json.loads(request.content)
        result: dict[str, Any] = {"resultType": "complete"}
        if payload["method"] == "server/discover":
            result["supportedVersions"] = ["2026-07-28"]
        elif payload["method"] == "tools/list":
            result["tools"] = [{
                "name": "jamf_get_setup_status",
                "securitySchemes": [{"type": "oauth2", "scopes": ["jamf:read"]}],
            }]
        else:
            params = payload["params"]
            assert request.headers["Mcp-Name"] == params["name"]
            tool_calls.append({"name": params["name"], "arguments": params["arguments"]})
            result["structuredContent"] = {"success": True, "data": "private-tenant-data"}
            if params["name"] == "jamf_get_computer" and failure:
                result["isError"] = failure == "isError"
                result["structuredContent"] = {"success": False, "error": "private-backend-error"}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": result})

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(probe.httpx, "AsyncClient", lambda **kwargs: client)
    config = (RemoteAuthConfig(ISSUER, RESOURCE, RESOURCE) if auth_mode == "oauth"
              else probe.BearerProbeConfig(RESOURCE))
    backends = ["jamf_pro", "jamf_protect", "jamf_security", "jamf_pro"]
    if failure:
        with pytest.raises(ValueError, match="jamf_get_computer"):
            await probe.validate(config, "private-token", backends)
        assert len(tool_calls) == 2
    else:
        await probe.validate(config, "private-token", backends)
        assert tool_calls == [
            {"name": "jamf_get_setup_status", "arguments": {}},
            {"name": "jamf_get_computer", "arguments": {"page": 0, "page_size": 1}},
            {"name": "jamf_protect_list_computers", "arguments": {"limit": 1}},
            {"name": "jamf_get_risk_devices", "arguments": {"page": 0, "page_size": 1}},
        ]
    output = capsys.readouterr().out
    if not failure:
        assert "PASS authenticated jamf_get_risk_devices" in output
    for private in ["private-token", "private-tenant-data", "private-backend-error"]:
        assert private not in output


@pytest.mark.parametrize("backends, token, message", [
    (["jamf_pro"], None, "require JAMF_MCP_VALIDATION_TOKEN"),
    (["jamf_override_device_risk"], "private-token", "Unknown backend"),
])
async def test_backend_selection_fails_before_network(
    monkeypatch: pytest.MonkeyPatch, backends: list[str], token: str | None, message: str
) -> None:
    """Missing credentials and arbitrary tool selections cannot issue any requests."""
    def unexpected_client(**kwargs: Any) -> None:
        pytest.fail("Invalid selection opened an HTTP client")

    monkeypatch.setattr(probe.httpx, "AsyncClient", unexpected_client)
    with pytest.raises(ValueError, match=message):
        await probe.validate(probe.BearerProbeConfig(RESOURCE), token, backends)


@pytest.mark.parametrize("version", [None, "1.0"])
async def test_probe_rejects_invalid_jsonrpc_version(
    monkeypatch: pytest.MonkeyPatch, version: str | None
) -> None:
    """Otherwise successful reads cannot pass with a missing or wrong protocol version."""
    def respond(request: httpx.Request) -> httpx.Response:
        if "authorization" not in request.headers:
            return httpx.Response(401, headers={"www-authenticate": 'Bearer scope="jamf:read"'})
        payload = json.loads(request.content)
        response = {
            "id": payload["id"],
            "result": {"resultType": "complete", "supportedVersions": ["2026-07-28"]},
        }
        if version:
            response["jsonrpc"] = version
        return httpx.Response(200, json=response)

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(probe.httpx, "AsyncClient", lambda **kwargs: client)
    with pytest.raises(ValueError, match="Invalid modern JSON-RPC"):
        await probe.validate(probe.BearerProbeConfig(RESOURCE), "private-token")


@pytest.mark.parametrize("issuers", [ISSUER, [ISSUER, 42], {ISSUER: True}, None])
async def test_probe_rejects_invalid_authorization_server_metadata(
    monkeypatch: pytest.MonkeyPatch, issuers: Any
) -> None:
    """A string containing the issuer cannot masquerade as an issuer array."""
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={
            "resource": RESOURCE,
            "authorization_servers": issuers,
            "scopes_supported": ["jamf:read"],
        })
    ))
    monkeypatch.setattr(probe.httpx, "AsyncClient", lambda **kwargs: client)
    with pytest.raises(ValueError, match="does not advertise"):
        await probe.validate(RemoteAuthConfig(ISSUER, RESOURCE, RESOURCE), "private-token")
