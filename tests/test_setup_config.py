"""Keep setup URL examples aligned with the endpoints used by product clients."""

import json

from mcp import Client
from mcp.server import MCPServer

from jamf_mcp.tools import register_all_tools


async def test_setup_help_urls_match_product_client_endpoints() -> None:
    """Help examples are tenant/API roots that compose into the real endpoints."""
    server = MCPServer("setup-config-test")
    register_all_tools(server)

    async with Client(server) as client:
        result = await client.call_tool("jamf_configure_help")

    assert not result.is_error
    help_data = json.loads(result.content[0].text)["data"]
    protect_url = help_data["jamf_protect"]["environment_variables"]["JAMF_PROTECT_URL"]["example"]
    security_url = help_data["jamf_security_cloud"]["environment_variables"]["JAMF_SECURITY_URL"][
        "example"
    ]

    # Protect appends these paths to the configured tenant URL.
    assert f"{protect_url}/token" == "https://yourorg.protect.jamfcloud.com/token"
    assert f"{protect_url}/graphql" == "https://yourorg.protect.jamfcloud.com/graphql"

    # Security Cloud authenticates and calls the RISK API from the API root.
    assert f"{security_url}/v1/login" == "https://api.wandera.com/v1/login"
    assert f"{security_url}/risk/v1/devices" == "https://api.wandera.com/risk/v1/devices"
