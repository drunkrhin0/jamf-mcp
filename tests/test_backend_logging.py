"""Keep backend diagnostics useful without logging private response content."""

import httpx
import pytest
from backend_helpers import MockedClients, make_server
from mcp import Client

from jamf_mcp.auth import JamfAuth, TokenInfo
from jamf_mcp.tools._common import set_client, set_protect_client, set_security_client

PRIVATE_MARKER = "private-backend-diagnostic-4e81"


@pytest.mark.parametrize(
    ("product", "tool_name", "arguments"),
    [
        ("jamf_pro", "jamf_create_category", {"name": "Restricted"}),
        ("jamf_pro", "jamf_create_printer", {"name": "Restricted", "uri": "lpd://printer"}),
        ("jamf_protect", "jamf_protect_get_alert", {"uuid": "alert-7"}),
        ("jamf_security_cloud", "jamf_get_risk_devices", {}),
    ],
)
async def test_http_failure_logs_keep_status_without_response_body(
    mocked_clients: MockedClients,
    caplog: pytest.LogCaptureFixture,
    product: str,
    tool_name: str,
    arguments: dict[str, object],
) -> None:
    """MCP tools retain their backend error details while logs omit response text."""

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": PRIVATE_MARKER})

    client = {
        "jamf_pro": mocked_clients.jamf_pro,
        "jamf_protect": mocked_clients.protect,
        "jamf_security_cloud": mocked_clients.security,
    }[product](respond)
    if product == "jamf_pro":
        set_client(client)
    elif product == "jamf_protect":
        set_protect_client(client)
    else:
        set_security_client(client)

    async with Client(make_server()) as mcp_client:
        result = await mcp_client.call_tool(tool_name, arguments)

    assert result.is_error
    assert "403" in str(result.structured_content)
    assert PRIVATE_MARKER not in caplog.text
    if product != "jamf_protect":
        assert PRIVATE_MARKER in str(result.structured_content["details"])


async def test_graphql_error_logs_count_but_keeps_error_for_tool_caller(
    mocked_clients: MockedClients,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """GraphQL error messages remain in tool output and stay out of backend logs."""

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"errors": [{"message": PRIVATE_MARKER}], "data": {"getAlert": None}},
        )

    set_protect_client(mocked_clients.protect(respond))
    async with Client(make_server()) as mcp_client:
        result = await mcp_client.call_tool("jamf_protect_get_alert", {"uuid": "alert-7"})

    assert result.is_error
    assert result.structured_content["graphql_errors"][0]["message"] == PRIVATE_MARKER
    assert "getAlert" in caplog.text
    assert "1 errors" in caplog.text
    assert PRIVATE_MARKER not in caplog.text


@pytest.mark.parametrize(
    ("product", "tool_name", "arguments"),
    [
        ("jamf_pro", "jamf_create_category", {"name": "Restricted"}),
        ("jamf_pro", "jamf_create_printer", {"name": "Restricted", "uri": "lpd://printer"}),
        ("jamf_protect", "jamf_protect_get_alert", {"uuid": "alert-7"}),
        ("jamf_security_cloud", "jamf_get_risk_devices", {}),
    ],
)
async def test_transport_failure_logs_exception_class_without_error_text(
    mocked_clients: MockedClients,
    caplog: pytest.LogCaptureFixture,
    product: str,
    tool_name: str,
    arguments: dict[str, object],
) -> None:
    """Backend transport errors preserve tool details but redact logs."""

    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(PRIVATE_MARKER, request=request)

    client = {
        "jamf_pro": mocked_clients.jamf_pro,
        "jamf_protect": mocked_clients.protect,
        "jamf_security_cloud": mocked_clients.security,
    }[product](respond)
    if product == "jamf_pro":
        set_client(client)
    elif product == "jamf_protect":
        set_protect_client(client)
    else:
        set_security_client(client)

    async with Client(make_server()) as mcp_client:
        result = await mcp_client.call_tool(tool_name, arguments)

    assert result.is_error
    assert PRIVATE_MARKER in str(result.structured_content)
    assert "ConnectError" in caplog.text
    assert PRIVATE_MARKER not in caplog.text


@pytest.mark.parametrize("product", ["jamf_pro", "jamf_protect", "jamf_security_cloud"])
@pytest.mark.parametrize("failure", ["http", "transport"])
async def test_authentication_failures_do_not_log_response_or_transport_text(
    mocked_clients: MockedClients,
    caplog: pytest.LogCaptureFixture,
    product: str,
    failure: str,
) -> None:
    """Production tools log auth status or exception class without private text."""

    def respond(request: httpx.Request) -> httpx.Response:
        if failure == "transport":
            raise httpx.ConnectError(PRIVATE_MARKER, request=request)
        return httpx.Response(403, json={"message": PRIVATE_MARKER})

    client = mocked_clients.auth_backed_client(product, respond)
    if product == "jamf_pro":
        set_client(client)
        tool_name, arguments = "jamf_get_buildings", {}
    elif product == "jamf_protect":
        set_protect_client(client)
        tool_name, arguments = "jamf_protect_get_alert", {"uuid": "alert-7"}
    else:
        set_security_client(client)
        tool_name, arguments = "jamf_get_risk_devices", {}

    async with Client(make_server()) as mcp_client:
        result = await mcp_client.call_tool(tool_name, arguments)

    assert result.is_error
    assert PRIVATE_MARKER not in caplog.text
    if failure == "http":
        assert "403" in caplog.text
    else:
        assert "ConnectError" in caplog.text


async def test_token_invalidation_logs_only_exception_class(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed token invalidation does not log arbitrary transport diagnostics."""

    auth = JamfAuth("https://pro.example.test", "test-id", "test-secret")
    auth._token = TokenInfo("test-token", expires_at=9_999_999_999)

    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(PRIVATE_MARKER, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
        await auth.invalidate_token(client)

    assert auth._token is None
    assert "ConnectError" in caplog.text
    assert PRIVATE_MARKER not in caplog.text
