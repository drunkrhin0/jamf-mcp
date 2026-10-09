"""Exercise the private plugin's actual server launch configuration."""

import json
import os
import shutil
import sysconfig
from pathlib import Path

import pytest
from mcp import Client, MCPError, StdioServerParameters

PLUGIN_ROOT = Path(__file__).resolve().parents[1] / "plugins" / "jamf-read-only"


@pytest.mark.parametrize("mode", ["2026-07-28", "legacy"])
async def test_plugin_stdio_read_only_contract(mode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The packaged command overrides defaults and refuses a direct write."""
    config = json.loads((PLUGIN_ROOT / "mcp.json").read_text())["mcpServers"]["jamf"]
    assert config["type"] == "stdio"
    executable = shutil.which(
        config["command"], path=sysconfig.get_path("scripts") + os.pathsep + os.defpath
    )
    assert executable, "Install the project with uv sync --extra dev before running checks"
    monkeypatch.setenv("JAMF_MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("JAMF_PRODUCTS", "protect,security")
    monkeypatch.setenv("JAMF_TOOL_FILTER", "complex")
    parameters = StdioServerParameters(command=executable, args=config["args"])
    async with Client(parameters, mode=mode, read_timeout_seconds=10) as client:
        tools = (await client.list_tools()).tools
        names = {tool.name for tool in tools}
        assert {"jamf_get_computer", "jamf_platform_get_benchmarks", "search_jamf_api"} <= names
        assert "jamf_protect_list_alerts" not in names
        assert "jamf_get_risk_devices" not in names
        assert all(tool.annotations.read_only_hint is True for tool in tools)
        result = await client.call_tool("jamf_get_setup_status")
        assert not result.is_error
        assert result.structured_content["success"] is True
        assert result.structured_content["data"]["summary"]["products_ready"] == 0
        with pytest.raises(MCPError, match="Unknown tool"):
            await client.call_tool("jamf_update_computer", {"computer_id": 42})


@pytest.fixture
def packager():
    """Load the standalone packaging helper without adding runtime dependencies."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "plugin_packager", PLUGIN_ROOT.parents[1] / "scripts" / "package_openai_plugin.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("connection", ["url", "app_id"])
def test_shared_package_connection(connection, tmp_path, packager):
    """Remote packages use one connection and retain every shared workflow."""
    output = tmp_path / "package"
    value = "https://jamf.example.com/mcp" if connection == "url" else "plugin_asdk_app_test"
    packager.package_plugin(output, **{connection: value})
    manifest = json.loads((output / "plugin.json").read_text())
    extension = manifest["extensions"]["com.openai"]
    assert (output / extension["onboardingSkill"]).is_file()
    source_skills = sorted((PLUGIN_ROOT / "skills").rglob("SKILL.md"))
    assert len(list((output / "skills").rglob("SKILL.md"))) == len(source_skills)
    for source in source_skills:
        assert (output / source.relative_to(PLUGIN_ROOT)).read_bytes() == source.read_bytes()
    if connection == "url":
        config = json.loads((output / "mcp.json").read_text())
        assert config["mcpServers"]["jamf"] == {"type": "streamable-http", "url": value}
        assert not (output / ".app.json").exists()
    else:
        assert extension["apps"] == "./.app.json"
        config = json.loads((output / ".app.json").read_text())
        assert config["apps"]["jamf"] == {"id": value, "required": True}
        assert not (output / "mcp.json").exists()
    assert not list(output.rglob(".env*"))
    original = (output / "plugin.json").read_bytes()
    with pytest.raises(FileExistsError):
        packager.package_plugin(output, **{connection: value})
    assert (output / "plugin.json").read_bytes() == original


@pytest.mark.parametrize(
    "connection",
    [
        {},
        {"url": "https://jamf.example.com/mcp", "app_id": "plugin_asdk_app_test"},
        {"url": "http://jamf.example.com/mcp"},
        {"url": "https://user:secret@jamf.example.com/mcp"},
        {"url": "https://jamf.example.com/mcp?token=secret"},
        {"url": "https://localhost:8443/mcp"},
        {"url": "https://jamf.example.com"},
        {"app_id": "made-up-id"},
    ],
)
def test_shared_package_rejects_invalid_connection(connection, tmp_path, packager):
    """Invalid connection metadata must fail before creating a distributable artifact."""
    output = tmp_path / "package"
    with pytest.raises(ValueError):
        packager.package_plugin(output, **connection)
    assert not output.exists()
