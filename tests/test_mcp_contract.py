"""Exercise production tools through modern and legacy MCP clients."""

import json
import sys
from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import Client, MCPError, StdioServerParameters
from mcp.server import MCPServer

from jamf_mcp.client import JamfAPIError
from jamf_mcp.prompts import register_prompts
from jamf_mcp.tools import get_registered_tools, register_all_tools
from jamf_mcp.tools._common import set_client


def make_server() -> MCPServer:
    """Build the production catalogue without creating live clients."""
    server = MCPServer("contract-test")
    register_all_tools(server)
    register_prompts(server)
    return server


@pytest.mark.parametrize("mode", ["2026-07-28", "legacy"])
async def test_discovery_and_results(mode: str) -> None:
    """Both protocol eras preserve schema, safety hints, prompts, and errors."""
    async with Client(make_server(), mode=mode) as client:
        tools = (await client.list_tools()).tools
        assert len(tools) == 68
        by_name = {tool.name: tool for tool in tools}
        assert by_name["jamf_get_computer"].input_schema["properties"]["computer_id"]
        assert by_name["jamf_get_computer"].annotations.read_only_hint is True
        assert by_name["jamf_update_computer"].annotations.read_only_hint is False
        assert by_name["jamf_update_computer"].annotations.destructive_hint is True
        assert all(tool.annotations.open_world_hint is False for tool in tools)
        assert len((await client.list_prompts()).prompts) == 4
        assert (await client.get_prompt("it-administrator")).messages
        success = await client.call_tool("jamf_get_setup_status")
        assert success.is_error is False
        assert success.structured_content == json.loads(success.content[0].text)
        assert success.structured_content["data"]["summary"]["products_ready"] == 0
        error = await client.call_tool("jamf_configure_help", {"product": "unknown"})
        assert error.is_error is True
        assert error.structured_content["success"] is False


def example_value(schema: dict) -> Any:
    """Generate harmless required input values from the published schema."""
    if "anyOf" in schema:
        return example_value(schema["anyOf"][0])
    return {
        "string": "test",
        "integer": 1,
        "number": 1,
        "boolean": False,
        "array": [],
        "object": {},
    }.get(schema.get("type"))


@pytest.mark.parametrize(
    "name",
    [
        func.__name__
        for func, _ in get_registered_tools()
        if func.__module__.split(".")[-1] not in {"setup", "docs"}
    ],
)
async def test_unconfigured_tools_report_execution_errors(name: str) -> None:
    """Every product tool handles missing configuration at the MCP interface."""
    async with Client(make_server()) as client:
        tools = (await client.list_tools()).tools
        schema = next(tool.input_schema for tool in tools if tool.name == name)
        arguments = {
            key: example_value(schema["properties"][key]) for key in schema.get("required", [])
        }
        result = await client.call_tool(name, arguments)
        assert result.is_error, name
        assert result.structured_content["success"] is False
        assert "setup" in result.structured_content


async def test_upstream_failure_keeps_actionable_details() -> None:
    """A Jamf failure remains a tool execution failure after protocol encoding."""
    mock_client = AsyncMock()
    mock_client.v1_get.side_effect = JamfAPIError("Forbidden", 403, '{"message":"Denied"}')
    set_client(mock_client)
    async with Client(make_server()) as client:
        result = await client.call_tool("jamf_get_computer")
    assert result.is_error
    assert result.structured_content["status_code"] == 403
    assert result.structured_content["details"]["message"] == "Denied"


@pytest.mark.parametrize("mode", ["2026-07-28", "legacy"])
async def test_real_stdio_startup(mode: str) -> None:
    """Run the installed entrypoint, not just imported functions."""
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "jamf_mcp.server", "--products", "protect"]
    )
    async with Client(parameters, mode=mode, read_timeout_seconds=10) as client:
        names = {tool.name for tool in (await client.list_tools()).tools}
        assert len(names) == 8
        assert "jamf_get_computer" not in names
        assert "jamf_protect_list_alerts" in names
        result = await client.call_tool("jamf_get_setup_status")
        assert not result.is_error


@pytest.mark.parametrize("mode", ["2026-07-28", "legacy"])
async def test_read_only_server_excludes_and_rejects_writes(mode: str) -> None:
    """A direct write call cannot bypass the read-only catalogue."""
    from jamf_mcp.server import create_server

    async with Client(create_server(read_only=True, products=["pro"]), mode=mode) as client:
        tools = (await client.list_tools()).tools
        names = {tool.name for tool in tools}
        assert "jamf_get_computer" in names
        assert "jamf_update_computer" not in names
        assert "jamf_create_api_client_credentials" not in names
        assert all(tool.annotations.read_only_hint is True for tool in tools)
        with pytest.raises(MCPError, match="Unknown tool"):
            await client.call_tool("jamf_update_computer", {"computer_id": "1"})


async def test_computer_detail_uses_documented_endpoint() -> None:
    """Catch endpoint drift in the actual tool rather than a parallel HTTP test."""
    mock_client = AsyncMock()
    mock_client.v1_get.return_value = {"id": "42", "general": {"name": "Mac"}}
    set_client(mock_client)
    async with Client(make_server()) as client:
        result = await client.call_tool("jamf_get_computer", {"computer_id": 42})
    assert not result.is_error
    assert result.structured_content["data"]["id"] == "42"
    mock_client.v1_get.assert_awaited_once_with("computers-inventory-detail/42")


async def test_cleanup_closes_all_clients_even_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """One close failure must not leak other clients or stale references."""
    from jamf_mcp import server
    from jamf_mcp.tools._common import (
        is_platform_available,
        is_pro_available,
        is_protect_available,
        is_security_available,
    )

    clients = [AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()]
    clients[2].close.side_effect = RuntimeError("close failed")
    monkeypatch.setattr(
        server,
        "get_configuration_status",
        lambda: {
            "pro_configured": True,
            "protect_configured": True,
            "security_configured": True,
            "platform_configured": True,
        },
    )
    for name, mock_client in zip(
        ["_init_pro_client", "_init_protect_client", "_init_security_client"], clients[:3]
    ):
        monkeypatch.setattr(server, name, lambda value=mock_client: value)
    monkeypatch.setattr(server.PlatformClient, "from_env", lambda: clients[3])
    with pytest.raises(RuntimeError, match="close failed"):
        async with server.jamf_lifespan(server.mcp):
            pass
    for mock_client in clients:
        mock_client.close.assert_awaited_once()
    assert not any(
        [
            is_pro_available(),
            is_protect_available(),
            is_security_available(),
            is_platform_available(),
        ]
    )


async def test_complex_filter_keeps_onboarding_tools() -> None:
    """Onboarding remains callable even when no matching product tools exist."""
    server = MCPServer("filtered")
    register_all_tools(server, tool_filter="complex", allowed_products=["pro"])
    async with Client(server) as client:
        names = {tool.name for tool in (await client.list_tools()).tools}
    assert {"jamf_get_setup_status", "jamf_configure_help"} <= names


@pytest.mark.parametrize("options", [{"tool_filter": "bad"}, {"allowed_products": ["bad"]}])
def test_invalid_catalogue_filters_fail_explicitly(options: dict) -> None:
    """Misconfiguration cannot silently remove all advertised tools."""
    with pytest.raises(ValueError, match="Unknown"):
        register_all_tools(MCPServer("invalid"), **options)


@pytest.mark.parametrize("mode", ["2026-07-28", "legacy"])
async def test_unknown_tools_are_protocol_errors(mode: str) -> None:
    """Tool catalogue failures must not become execution error results."""
    async with Client(make_server(), mode=mode) as client:
        with pytest.raises(MCPError) as error:
            await client.call_tool("nonexistent_tool")
    assert error.value.error.code == -32602
