"""Verify the documentation adapter without contacting the upstream server."""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import Client, MCPError
from mcp_types import CallToolResult, ImageContent, ListToolsResult, TextContent, Tool

from jamf_mcp.server import create_server
from jamf_mcp.tools import docs as server

FORWARDING_CASES = [
    ("list_available_specs", {}, "list-specs", {}, {}),
    (
        "search_jamf_api",
        {"pattern": "example"},
        "search-endpoints",
        {"pattern": "example"},
        {"pattern": "example"},
    ),
    (
        "list_api_endpoints",
        {"spec_title": "Classic API"},
        "list-endpoints",
        {"title": "jamf-pro=Classic API"},
        {"spec_title": "Classic API"},
    ),
    *[
        (
            name,
            {"path": "/example", "method": "get"},
            upstream,
            {"path": "/example", "method": "GET", "title": "jamf-pro=Jamf Pro API"},
            {"path": "/example", "method": "get"},
        )
        for name, upstream in [
            ("get_endpoint_details", "get-endpoint"),
        ]
    ],
    (
        "call_jamf_docs_tool",
        {"tool_name": "list-specs", "arguments": "{}"},
        "list-specs",
        {},
        {"tool_name": "list-specs"},
    ),
]


@pytest.mark.parametrize("is_error", [False, True])
@pytest.mark.parametrize(
    "name,arguments,operation,upstream_arguments,error_context", FORWARDING_CASES
)
async def test_full_upstream_result_preserved(
    monkeypatch: pytest.MonkeyPatch,
    is_error: bool,
    name: str,
    arguments: dict[str, Any],
    operation: str,
    upstream_arguments: dict[str, Any],
    error_context: dict[str, Any],
) -> None:
    """Keep non-text content, metadata, structured data, and error status."""
    upstream = CallToolResult(
        content=[
            TextContent(type="text", text="documentation"),
            ImageContent(type="image", data="AA==", mime_type="image/png"),
        ],
        structured_content={"endpoint": "/api/v1/example"},
        is_error=is_error,
        meta={"source": "Jamf"},
    )
    forward = AsyncMock(return_value=upstream)
    monkeypatch.setattr(server, "call_upstream_tool", forward)
    async with Client(create_server()) as client:
        result = await client.call_tool(name, arguments)
    forward.assert_awaited_once_with(operation, upstream_arguments)
    assert result.content == upstream.content
    assert result.structured_content == upstream.structured_content
    assert result.is_error == upstream.is_error
    assert result.meta["source"] == "Jamf"


@pytest.mark.parametrize("arguments", ["[]", "null", '"string"', "invalid"])
async def test_generic_arguments_must_be_object(arguments: str) -> None:
    """Reject invalid input before connecting upstream."""
    async with Client(create_server()) as client:
        result = await client.call_tool(
            "call_jamf_docs_tool", {"tool_name": "list-specs", "arguments": arguments}
        )
    assert result.is_error


async def test_execution_proxy_not_exposed() -> None:
    """Documentation tools cannot forward arbitrary operations."""
    async with Client(create_server()) as client:
        result = await client.call_tool("call_jamf_docs_tool", {"tool_name": "execute-request"})
    assert result.is_error
    assert "Unsupported documentation tool" in result.content[0].text


async def test_discovery_all_pages_and_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    """Follow cursors and publish only approved documentation tools."""
    pages = [
        ListToolsResult(
            tools=[Tool(name="list-specs", input_schema={"type": "object"})], next_cursor="page2"
        ),
        ListToolsResult(
            tools=[
                Tool(name="search-endpoints", input_schema={"type": "object"}),
                Tool(name="execute-request", input_schema={"type": "object"}),
            ]
        ),
    ]
    upstream = AsyncMock()
    upstream.list_tools.side_effect = pages
    connection = AsyncMock()
    connection.__aenter__.return_value = upstream
    monkeypatch.setattr(server, "Client", lambda url: connection)
    monkeypatch.setattr(server, "_upstream_tools_cache", None)
    tools = await server.get_upstream_tools()
    assert [tool["name"] for tool in tools] == ["list-specs", "search-endpoints"]
    assert upstream.list_tools.await_args_list[1].kwargs == {"cursor": "page2"}
    assert await server.get_upstream_tools() == tools
    assert upstream.list_tools.await_count == 2


@pytest.mark.parametrize("mode", ["2026-07-28", "legacy"])
async def test_docs_stdio_startup(mode: str) -> None:
    """Verify documentation tools ship in the main server in either protocol era."""
    import sys

    from mcp import StdioServerParameters

    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "jamf_mcp.server", "--products", "docs", "--read-only"],
    )
    async with Client(parameters, mode=mode, read_timeout_seconds=10) as client:
        assert len((await client.list_tools()).tools) == 11
        result = await client.call_tool("call_jamf_docs_tool", {"tool_name": "execute-request"})
        assert result.is_error


@pytest.mark.parametrize("mode", ["2026-07-28", "legacy"])
async def test_unknown_docs_tool_is_protocol_error(mode: str) -> None:
    """Reject unknown local wrapper names before opening an upstream session."""
    async with Client(create_server(), mode=mode) as client:
        with pytest.raises(MCPError) as error:
            await client.call_tool("nonexistent_tool")
    assert error.value.error.code == -32602


@pytest.mark.parametrize(
    "name,arguments,operation,upstream_arguments,error_context", FORWARDING_CASES
)
async def test_forwarding_failure_preserves_local_context(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    arguments: dict[str, Any],
    operation: str,
    upstream_arguments: dict[str, Any],
    error_context: dict[str, Any],
) -> None:
    """All wrappers mark connection failures and retain their existing input context."""
    forward = AsyncMock(side_effect=ConnectionError("upstream unavailable"))
    monkeypatch.setattr(server, "call_upstream_tool", forward)
    async with Client(create_server()) as client:
        result = await client.call_tool(name, arguments)
    forward.assert_awaited_once_with(operation, upstream_arguments)
    assert result.is_error
    assert result.structured_content == {"error": "upstream unavailable", **error_context}


@pytest.mark.parametrize(
    "options,docs_count",
    [
        ({}, 9),
        ({"products": ["docs"]}, 9),
        ({"products": ["jamf_docs"], "read_only": True}, 9),
        ({"products": ["pro", "platform", "docs"], "read_only": True}, 9),
        ({"products": ["pro"]}, 0),
        ({"tool_filter": "complex"}, 0),
    ],
)
async def test_docs_catalogue_respects_filters(options: dict, docs_count: int) -> None:
    """The main endpoint includes docs only when selected by its shared filters."""
    from jamf_mcp.tools import get_registered_tools

    docs_names = {
        func.__name__ for func, _ in get_registered_tools() if func.__module__ == server.__name__
    }
    async with Client(create_server(**options)) as client:
        tools = (await client.list_tools()).tools
        selected = [tool for tool in tools if tool.name in docs_names]
        assert len(selected) == docs_count
        assert all(tool.annotations.read_only_hint is True for tool in selected)
        assert all(tool.annotations.destructive_hint is False for tool in selected)
        if docs_count == 0:
            with pytest.raises(MCPError, match="Unknown tool"):
                await client.call_tool("search_jamf_api", {"pattern": "computers"})
        status = (await client.call_tool("jamf_get_setup_status")).structured_content["data"]
        assert status["documentation"]["requires_tenant_credentials"] is False
        assert status["documentation"]["upstream_access_verified"] is False
        assert status["summary"]["total_products"] == 4


@pytest.mark.parametrize("authenticated", [False, True])
async def test_docs_remote_read_only_endpoint(
    monkeypatch: pytest.MonkeyPatch, authenticated: bool
) -> None:
    """Compose's catalogue forwards documentation only after inbound authentication."""
    import json

    import httpx

    from jamf_mcp.remote import build_remote_http_app, build_remote_tool_scope_map

    token = "offline-docs-reader-token-with-at-least-32-characters"
    resource = "https://docs.example.test/mcp"
    monkeypatch.setenv("JAMF_MCP_REMOTE_AUTH_MODE", "bearer")
    monkeypatch.setenv("JAMF_MCP_RESOURCE_URL", resource)
    monkeypatch.setenv(
        "JAMF_MCP_BEARER_TOKENS_JSON",
        json.dumps([{"identity": "docs-reader", "token": token, "scopes": ["jamf:read"]}]),
    )
    result = CallToolResult(
        content=[TextContent(type="text", text="specification")],
        structured_content={"title": "Blueprints API"},
        meta={"source": "Jamf"},
    )
    forward = AsyncMock(return_value=result)
    monkeypatch.setattr(server, "call_upstream_tool", forward)
    assert build_remote_tool_scope_map()["list_available_specs"] == frozenset({"jamf:read"})
    endpoint = create_server(remote=True, read_only=True, products=["pro", "platform", "docs"])
    app = build_remote_http_app(endpoint, stateless_http=True, json_response=True)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2026-07-28",
        "Mcp-Method": "tools/call",
        "Mcp-Name": "list_available_specs",
    }
    if authenticated:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://docs.example.test"
    ) as client:
        async with app.router.lifespan_context(app):
            response = await client.post(
                "/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "list_available_specs",
                        "arguments": {},
                        "_meta": {
                            "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                            "io.modelcontextprotocol/clientInfo": {
                                "name": "docs-test", "version": "1.0"
                            },
                            "io.modelcontextprotocol/clientCapabilities": {},
                        },
                    },
                },
            )
    if authenticated:
        assert response.status_code == 200, response.text
        payload = response.json()["result"]
        assert payload["structuredContent"] == {"title": "Blueprints API"}
        assert payload["_meta"]["source"] == "Jamf"
        assert payload.get("isError", False) is False
        forward.assert_awaited_once_with("list-specs", {})
    else:
        assert response.status_code == 401
        forward.assert_not_awaited()


@pytest.mark.parametrize("request_body", [False, True])
async def test_schema_lookup_uses_endpoint_documentation(
    monkeypatch: pytest.MonkeyPatch, request_body: bool
) -> None:
    """Current upstream schemas live in get-endpoint rather than separate tools."""
    import json

    method = "post" if request_body else "get"
    content = {"application/json": {"schema": {"$ref": "#/components/schemas/X"}}}
    operation = {"requestBody": {"content": content}, "responses": {"201": {"content": content}}}
    components = {"schemas": {"X": {"type": "object"}}}
    document = {"paths": {"/example": {method: operation}}, "components": components}
    upstream = CallToolResult(
        content=[TextContent(type="text", text=json.dumps(document))],
        meta={"source": "Jamf"},
    )
    forward = AsyncMock(return_value=upstream)
    monkeypatch.setattr(server, "call_upstream_tool", forward)
    tool = "get_request_body_schema" if request_body else "get_response_schema"
    arguments = {"path": "/example", "method": method}
    if not request_body:
        arguments["status_code"] = "201"
    async with Client(create_server()) as client:
        result = await client.call_tool(tool, arguments)
    forward.assert_awaited_once_with(
        "get-endpoint",
        {"path": "/example", "method": method.upper(), "title": "jamf-pro=Jamf Pro API"},
    )
    assert not result.is_error
    assert result.structured_content["components"] == components
    assert result.meta["source"] == "Jamf"
    if request_body:
        assert result.structured_content["requestBody"] == operation["requestBody"]
    else:
        assert result.structured_content["response"] == operation["responses"]["201"]


@pytest.mark.parametrize("tool", ["get_request_body_schema", "get_response_schema"])
async def test_schema_lookup_connection_failure(monkeypatch: pytest.MonkeyPatch, tool: str) -> None:
    forward = AsyncMock(side_effect=ConnectionError("upstream unavailable"))
    monkeypatch.setattr(server, "call_upstream_tool", forward)
    async with Client(create_server()) as client:
        result = await client.call_tool(tool, {"path": "/example", "method": "get"})
    assert result.is_error
    assert result.structured_content == {
        "error": "upstream unavailable", "path": "/example", "method": "get"
    }


@pytest.mark.parametrize("tool", ["get_request_body_schema", "get_response_schema"])
async def test_schema_lookup_reports_missing_documentation(
    monkeypatch: pytest.MonkeyPatch, tool: str
) -> None:
    upstream = CallToolResult(content=[], structured_content={"paths": {"/example": {"get": {}}}})
    monkeypatch.setattr(server, "call_upstream_tool", AsyncMock(return_value=upstream))
    async with Client(create_server()) as client:
        result = await client.call_tool(tool, {"path": "/example", "method": "get"})
    assert result.is_error
    assert "does not document" in result.structured_content["error"]
