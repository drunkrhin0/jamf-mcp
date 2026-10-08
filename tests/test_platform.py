"""Exercise read-only Jamf Platform behavior through the production MCP interface."""

import httpx
import pytest
from backend_helpers import make_server
from mcp import Client


async def test_blueprint_list_authenticates_for_its_environment() -> None:
    """Use gateway client credentials and send environment context on a paginated read."""
    from jamf_mcp.platform_client import PlatformClient
    from jamf_mcp.tools._common import set_platform_client

    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/auth/token":
            assert request.method == "POST"
            assert request.content == (
                b"grant_type=client_credentials&client_id=test-id&client_secret=test-secret"
            )
            return httpx.Response(200, json={"access_token": "platform-token", "expires_in": 900})
        assert request.method == "GET"
        assert request.url.path == "/blueprints/v1/blueprints"
        assert request.headers["authorization"] == "Bearer platform-token"
        assert request.headers["x-environment-id"] == "11111111-1111-4111-8111-111111111111"
        assert request.url.params["page"] == "2"
        assert request.url.params["page-size"] == "5"
        return httpx.Response(200, json={"totalCount": 1, "results": [{"id": "bp-1"}]})

    client = PlatformClient(
        "https://apac.api.jamfcloud.com",
        "11111111-1111-4111-8111-111111111111",
        "test-id",
        "test-secret",
        transport=httpx.MockTransport(respond),
    )
    set_platform_client(client)
    try:
        async with Client(make_server()) as mcp:
            result = await mcp.call_tool(
                "jamf_platform_get_blueprints", {"page": 2, "page_size": 5}
            )
        assert not result.is_error
        assert result.structured_content["data"]["results"] == [{"id": "bp-1"}]
        assert len(requests) == 2
    finally:
        set_platform_client(None)
        await client.close()


async def test_expired_gateway_token_is_replaced_and_then_cached() -> None:
    """A rejected gateway token is renewed once; following reads reuse the valid token."""
    from jamf_mcp.platform_client import PlatformClient
    from jamf_mcp.tools._common import set_platform_client

    token_count = 0
    read_count = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal token_count, read_count
        if request.url.path == "/auth/token":
            token_count += 1
            return httpx.Response(
                200,
                json={"access_token": f"reader-{token_count}", "expires_in": 900},
            )
        read_count += 1
        if read_count == 1:
            return httpx.Response(401)
        assert request.headers["authorization"] == "Bearer reader-2"
        return httpx.Response(200, json={"benchmarks": []})

    client = PlatformClient(
        "https://us.api.jamfcloud.com",
        "11111111-1111-4111-8111-111111111111",
        "id",
        "secret",
        transport=httpx.MockTransport(respond),
    )
    set_platform_client(client)
    try:
        async with Client(make_server()) as mcp:
            first = await mcp.call_tool("jamf_platform_get_benchmarks")
            second = await mcp.call_tool("jamf_platform_get_benchmarks")
        assert not first.is_error and not second.is_error
        assert token_count == 2
        assert read_count == 3
    finally:
        set_platform_client(None)
        await client.close()


@pytest.mark.parametrize("failure", ["auth", "read", "redirect", "malformed_token"])
async def test_platform_failures_are_errors_without_secret_content(
    failure: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Permission and authentication failures stay error-marked and omit private bodies."""
    from jamf_mcp.platform_client import PlatformClient
    from jamf_mcp.tools._common import set_platform_client

    marker = "private-upstream-secret-marker"

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/token":
            if failure == "auth":
                return httpx.Response(401, json={"error": marker})
            if failure == "malformed_token":
                return httpx.Response(200, json={"access_token": marker, "expires_in": "invalid"})
            return httpx.Response(200, json={"access_token": "reader", "expires_in": 900})
        assert request.url.host == "us.api.jamfcloud.com"
        if failure == "redirect":
            return httpx.Response(302, headers={"Location": "https://attacker.example.test"})
        return httpx.Response(403, json={"error": marker})

    client = PlatformClient(
        "https://us.api.jamfcloud.com",
        "11111111-1111-4111-8111-111111111111",
        "id",
        "secret",
        transport=httpx.MockTransport(respond),
    )
    set_platform_client(client)
    try:
        async with Client(make_server()) as mcp:
            result = await mcp.call_tool("jamf_platform_get_benchmarks")
        assert result.is_error
        assert result.structured_content["success"] is False
        assert marker not in str(result.structured_content)
        assert marker not in caplog.text
        if failure != "malformed_token":
            assert (
                result.structured_content["status_code"]
                == {
                    "auth": 401,
                    "read": 403,
                    "redirect": 302,
                }[failure]
            )
    finally:
        set_platform_client(None)
        await client.close()


async def test_invalid_blueprint_id_fails_before_authentication() -> None:
    """Blueprint IDs must be UUIDs; invalid identifiers cause no upstream requests."""
    from jamf_mcp.platform_client import PlatformClient
    from jamf_mcp.tools._common import set_platform_client

    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"access_token": "reader", "expires_in": 900})

    client = PlatformClient(
        "https://us.api.jamfcloud.com",
        "11111111-1111-4111-8111-111111111111",
        "id",
        "secret",
        transport=httpx.MockTransport(respond),
    )
    set_platform_client(client)
    try:
        async with Client(make_server()) as mcp:
            result = await mcp.call_tool(
                "jamf_platform_get_blueprints", {"blueprint_id": "not-a-uuid"}
            )
        assert result.is_error
        assert requests == []
    finally:
        set_platform_client(None)
        await client.close()


@pytest.mark.parametrize(
    ("tool", "arguments", "path", "query"),
    [
        (
            "jamf_platform_get_declarations",
            {
                "device_id": "11111111-1111-4111-8111-111111111111",
                "filter": "active==true",
                "page": 1,
                "page_size": 10,
            },
            "/ddm/report/v1/devices/11111111-1111-4111-8111-111111111111/declarations",
            {"filter": "active==true", "page": "1", "size": "10"},
        ),
        (
            "jamf_platform_get_declarations",
            {
                "declaration_identifier": "Blueprint_test",
                "filter": "channel==SYSTEM",
                "page_size": 5,
            },
            "/ddm/report/v1/declarations/Blueprint_test/devices",
            {"filter": "channel==SYSTEM", "page": "0", "size": "5"},
        ),
        (
            "jamf_platform_get_device_channels",
            {"device_id": "11111111-1111-4111-8111-111111111111"},
            "/ddm/report/v1/devices/11111111-1111-4111-8111-111111111111/channels",
            {},
        ),
    ],
)
async def test_declaration_reports_use_platform_device_context(
    tool: str,
    arguments: dict,
    path: str,
    query: dict,
) -> None:
    """Read DDM reports using the required filter and reporting-specific pagination."""
    from jamf_mcp.platform_client import PlatformClient
    from jamf_mcp.tools._common import set_platform_client

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/token":
            return httpx.Response(200, json={"access_token": "reader", "expires_in": 900})
        assert request.method == "GET"
        assert request.url.path == path
        assert dict(request.url.params) == query
        return httpx.Response(200, json={"results": [{"validityState": "INVALID"}]})

    client = PlatformClient(
        "https://us.api.jamfcloud.com",
        "11111111-1111-4111-8111-111111111111",
        "id",
        "secret",
        transport=httpx.MockTransport(respond),
    )
    set_platform_client(client)
    try:
        async with Client(make_server()) as mcp:
            result = await mcp.call_tool(tool, arguments)
        assert not result.is_error
        assert result.structured_content["data"]["results"][0]["validityState"] == "INVALID"
    finally:
        set_platform_client(None)
        await client.close()


async def test_server_exposes_and_initializes_platform_as_a_separate_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Platform-only startup reports readiness and closes its HTTP pool on shutdown."""
    from jamf_mcp.server import create_server

    for name, value in {
        "JAMF_PLATFORM_URL": "https://us.api.jamfcloud.com",
        "JAMF_PLATFORM_ENVIRONMENT_ID": "11111111-1111-4111-8111-111111111111",
        "JAMF_PLATFORM_CLIENT_ID": "test-id",
        "JAMF_PLATFORM_CLIENT_SECRET": "test-secret",
    }.items():
        monkeypatch.setenv(name, value)
    async with Client(create_server(products=["platform"], read_only=True)) as mcp:
        tools = (await mcp.list_tools()).tools
        names = {tool.name for tool in tools}
        assert "jamf_platform_get_blueprints" in names
        assert "jamf_get_computer" not in names
        assert all(tool.annotations.read_only_hint for tool in tools)
        status = (await mcp.call_tool("jamf_get_setup_status")).structured_content["data"]
        assert status["jamf_platform"]["ready"] is True
        assert status["summary"]["total_products"] == 4
        assert status["summary"]["products_ready"] == 1
    # The public setup interface must not report a stale ready client after shutdown.
    async with Client(make_server()) as mcp:
        status = (await mcp.call_tool("jamf_get_setup_status")).structured_content["data"]
        assert status["jamf_platform"]["ready"] is False


@pytest.mark.parametrize(
    ("tool", "arguments", "path", "query", "body"),
    [
        (
            "jamf_platform_get_benchmark_rules",
            {"benchmark_id": "bench-1", "page": 1, "page_size": 5, "search": "firewall"},
            "/compliance-benchmarks/v1/benchmarks/bench-1/rules",
            {"page": "1", "page-size": "5", "rule-search": "firewall"},
            {"totalCount": 1, "results": [{"id": "rule-1", "failedDevices": 2}]},
        ),
        (
            "jamf_platform_get_benchmark_devices",
            {
                "benchmark_id": "bench-1",
                "rule_id": "rule-1",
                "rule_result": "FAILED",
                "page_size": 5,
            },
            "/compliance-benchmarks/v1/benchmarks/bench-1/devices",
            {"page": "0", "page-size": "5", "rule-id": "rule-1", "rule-result": "FAILED"},
            {"totalCount": 1, "results": [{"deviceId": "device-1", "state": "FAILED"}]},
        ),
        (
            "jamf_platform_get_benchmark_compliance",
            {"benchmark_id": "bench-1"},
            "/compliance-benchmarks/v1/benchmarks/bench-1/compliance-percentage",
            {},
            {"compliancePercentage": 75.5},
        ),
    ],
)
async def test_benchmark_reporting_returns_actual_results(
    tool: str,
    arguments: dict,
    path: str,
    query: dict,
    body: dict,
) -> None:
    """Preserve per-rule failures and aggregate percentages from documented reporting APIs."""
    from jamf_mcp.platform_client import PlatformClient
    from jamf_mcp.tools._common import set_platform_client

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/token":
            return httpx.Response(200, json={"access_token": "reader", "expires_in": 900})
        assert request.method == "GET"
        assert request.url.path == path
        assert dict(request.url.params) == query
        return httpx.Response(200, json=body)

    client = PlatformClient(
        "https://eu.api.jamfcloud.com",
        "11111111-1111-4111-8111-111111111111",
        "id",
        "secret",
        transport=httpx.MockTransport(respond),
    )
    set_platform_client(client)
    try:
        async with Client(make_server()) as mcp:
            result = await mcp.call_tool(tool, arguments)
        assert not result.is_error
        assert result.structured_content["data"] == body
    finally:
        set_platform_client(None)
        await client.close()


@pytest.mark.parametrize(
    ("arguments", "path"),
    [
        ({}, "/compliance-benchmarks/v1/benchmarks"),
        ({"benchmark_id": "bench-1"}, "/compliance-benchmarks/v1/benchmarks/bench-1"),
    ],
)
async def test_benchmarks_read_configuration(arguments: dict, path: str) -> None:
    """Benchmark lists have no invented pagination; detail reads preserve the definition."""
    from jamf_mcp.platform_client import PlatformClient
    from jamf_mcp.tools._common import set_platform_client

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/token":
            return httpx.Response(200, json={"access_token": "reader", "expires_in": 900})
        assert request.method == "GET"
        assert request.url.path == path
        assert not request.url.query
        return httpx.Response(200, json={"id": "bench-1", "name": "CIS test"})

    client = PlatformClient(
        "https://eu.api.jamfcloud.com",
        "11111111-1111-4111-8111-111111111111",
        "id",
        "secret",
        transport=httpx.MockTransport(respond),
    )
    set_platform_client(client)
    try:
        async with Client(make_server()) as mcp:
            result = await mcp.call_tool("jamf_platform_get_benchmarks", arguments)
        assert not result.is_error
        assert result.structured_content["data"] == {"id": "bench-1", "name": "CIS test"}
    finally:
        set_platform_client(None)
        await client.close()


async def test_platform_http_requires_reader_identity_and_excludes_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production HTTP denies anonymous calls and lets a reader invoke Platform GETs."""
    import json

    from jamf_mcp.platform_client import PlatformClient
    from jamf_mcp.remote import build_remote_http_app, build_remote_tool_scope_map
    from jamf_mcp.server import create_server
    from jamf_mcp.tools._common import set_platform_client

    reader_token = "r" * 48
    monkeypatch.setenv("JAMF_MCP_REMOTE_AUTH_MODE", "bearer")
    monkeypatch.setenv("JAMF_MCP_RESOURCE_URL", "https://mcp.example.test/mcp")
    monkeypatch.setenv(
        "JAMF_MCP_BEARER_TOKENS_JSON",
        json.dumps([{"identity": "reader", "token": reader_token, "scopes": ["jamf:read"]}]),
    )
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/auth/token":
            return httpx.Response(200, json={"access_token": "platform-token", "expires_in": 900})
        assert request.method == "GET"
        assert request.url.path == "/compliance-benchmarks/v1/benchmarks"
        return httpx.Response(200, json={"benchmarks": [{"id": "bench-1"}]})

    platform = PlatformClient(
        "https://us.api.jamfcloud.com",
        "11111111-1111-4111-8111-111111111111",
        "id",
        "secret",
        transport=httpx.MockTransport(respond),
    )
    server = create_server(remote=True, read_only=True, products=["pro", "platform"])
    app = build_remote_http_app(
        server,
        tool_scopes=build_remote_tool_scope_map(),
        stateless_http=True,
        json_response=True,
    )
    headers = {
        "Authorization": f"Bearer {reader_token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2026-07-28",
    }
    metadata = {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "platform-test", "version": "1"},
        "io.modelcontextprotocol/clientCapabilities": {},
    }
    call = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "jamf_platform_get_benchmarks", "arguments": {}, "_meta": metadata},
    }
    try:
        async with app.router.lifespan_context(app):
            set_platform_client(platform)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="https://mcp.example.test",
            ) as http:
                anonymous = await http.post("/mcp", json=call)
                assert anonymous.status_code == 401
                assert requests == []
                read = await http.post(
                    "/mcp",
                    headers={
                        **headers,
                        "Mcp-Method": "tools/call",
                        "Mcp-Name": "jamf_platform_get_benchmarks",
                    },
                    json=call,
                )
                assert read.status_code == 200
                assert read.json()["result"]["structuredContent"]["data"] == {
                    "benchmarks": [{"id": "bench-1"}],
                }
                listed = await http.post(
                    "/mcp",
                    headers={**headers, "Mcp-Method": "tools/list"},
                    json={
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/list",
                        "params": {"_meta": metadata},
                    },
                )
                tools = listed.json()["result"]["tools"]
                assert len([t for t in tools if t["name"].startswith("jamf_platform_")]) == 7
                assert all(t["annotations"]["readOnlyHint"] for t in tools)
                denied = await http.post(
                    "/mcp",
                    headers={
                        **headers,
                        "Mcp-Method": "tools/call",
                        "Mcp-Name": "jamf_update_computer",
                    },
                    json={
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {
                            "name": "jamf_update_computer",
                            "arguments": {"computer_id": "1"},
                            "_meta": metadata,
                        },
                    },
                )
                assert denied.status_code == 403
                assert len(requests) == 2
    finally:
        set_platform_client(None)
        await platform.close()
