"""Exercise representative production tools through MCP and mocked HTTP APIs."""

import json
import xml.etree.ElementTree as ET

import httpx
import pytest
from backend_helpers import MockedClients, make_server
from mcp import Client

from jamf_mcp.tools._common import set_client, set_protect_client, set_security_client


async def test_computer_list_sends_pagination_and_filter(
    mocked_clients: MockedClients,
) -> None:
    """Send the computer list page and serial filter to Jamf Pro v1."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"totalCount": 1, "results": [{"id": "42", "name": "Fleet Mac"}]},
        )

    set_client(mocked_clients.jamf_pro(respond))
    async with Client(make_server()) as client:
        result = await client.call_tool(
            "jamf_get_computer", {"serial_number": "SER-42", "page": 2, "page_size": 25}
        )

    assert not result.is_error
    assert result.structured_content["data"]["results"] == [{"id": "42", "name": "Fleet Mac"}]
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/api/v1/computers-inventory"
    assert requests[0].url.params["page"] == "2"
    assert requests[0].url.params["page-size"] == "25"
    assert requests[0].url.params["filter"] == 'hardware.serialNumber=="SER-42"'
    assert requests[0].headers["authorization"] == "Bearer pro-token"


async def test_computer_list_selects_serial_inventory_sections(
    mocked_clients: MockedClients,
) -> None:
    """Retrieve names and serials in one paginated read without full details."""
    body = {
        "totalCount": 1,
        "results": [
            {"id": "42", "general": {"name": "Fleet Mac"}, "hardware": {"serialNumber": "SER-42"}}
        ],
    }

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v1/computers-inventory"
        assert request.url.params.get_list("section") == ["GENERAL", "HARDWARE"]
        return httpx.Response(200, json=body)

    set_client(mocked_clients.jamf_pro(respond))
    async with Client(make_server()) as client:
        result = await client.call_tool(
            "jamf_get_computer", {"sections": ["GENERAL", "HARDWARE"], "page_size": 10}
        )
    assert not result.is_error
    assert result.structured_content["data"] == body


async def test_classic_building_read_returns_requested_page(
    mocked_clients: MockedClients,
) -> None:
    """Return the requested slice from the Classic API buildings response."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "buildings": [
                    {"id": 1, "name": "Perth"},
                    {"id": 2, "name": "Sydney"},
                    {"id": 3, "name": "Melbourne"},
                ]
            },
        )

    set_client(mocked_clients.jamf_pro(respond))
    async with Client(make_server()) as client:
        result = await client.call_tool("jamf_get_buildings", {"page": 1, "page_size": 1})

    assert not result.is_error
    assert result.structured_content["data"] == {
        "buildings": [{"id": 2, "name": "Sydney"}],
        "totalCount": 3,
    }
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/JSSResource/buildings"


async def test_protect_alert_list_uses_graphql_and_filters_results(
    mocked_clients: MockedClients,
) -> None:
    """Call Protect GraphQL and return only alerts matching requested filters."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": {
                    "listAlerts": {
                        "items": [
                            {"uuid": "a1", "severity": "High", "status": "New"},
                            {"uuid": "a2", "severity": "Low", "status": "New"},
                            {"uuid": "a3", "severity": "HIGH", "status": "Resolved"},
                        ]
                    }
                }
            },
        )

    set_protect_client(mocked_clients.protect(respond))
    async with Client(make_server()) as client:
        result = await client.call_tool(
            "jamf_protect_list_alerts", {"severity": "high", "status": "new", "limit": 1}
        )

    assert not result.is_error
    assert result.structured_content["data"]["items"] == [
        {"uuid": "a1", "severity": "High", "status": "New"}
    ]
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/graphql"
    assert requests[0].headers["authorization"] == "protect-token"
    body = json.loads(requests[0].content)
    assert "listAlerts" in body["query"]
    assert body["variables"] == {"input": {}}


@pytest.mark.parametrize(
    ("api_version", "path", "message"),
    [
        ("v1", "/risk/v1/devices", "Retrieved 1 of 41 devices with risk status (v1)"),
        ("v2", "/risk/v2/devices", "Retrieved 1 devices with risk status (v2)"),
    ],
)
async def test_security_risk_read_sends_pagination(
    mocked_clients: MockedClients,
    api_version: str,
    path: str,
    message: str,
) -> None:
    """Pass versioned RISK API pagination parameters through the MCP tool."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "records": [{"deviceId": "device-7", "risk": "HIGH"}],
                "pagination": {"totalRecords": 41},
            },
        )

    set_security_client(mocked_clients.security(respond))
    async with Client(make_server()) as client:
        result = await client.call_tool(
            "jamf_get_risk_devices",
            {"api_version": api_version, "page": 3, "page_size": 10},
        )

    assert not result.is_error
    assert result.structured_content["data"]["records"][0]["deviceId"] == "device-7"
    assert result.structured_content["message"] == message
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == path
    assert requests[0].url.params["page"] == "3"
    assert requests[0].url.params["pageSize"] == "10"
    assert requests[0].headers["authorization"] == "Bearer security-token"


async def test_create_category_posts_expected_json_payload(
    mocked_clients: MockedClients,
) -> None:
    """Create a Jamf Pro category with the selected priority."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": 12, "name": "Security"})

    set_client(mocked_clients.jamf_pro(respond))
    async with Client(make_server()) as client:
        result = await client.call_tool("jamf_create_category", {"name": "Security", "priority": 4})

    assert not result.is_error
    assert result.structured_content["data"] == {"id": 12, "name": "Security"}
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/api/v1/categories"
    assert json.loads(requests[0].content) == {"name": "Security", "priority": 4}


async def test_update_computer_sends_partial_patch_payload(
    mocked_clients: MockedClients,
) -> None:
    """Map provided computer fields to Jamf's PATCH request body."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"general": {"name": "Renamed Mac", "serialNumber": "SER-42"}},
        )

    set_client(mocked_clients.jamf_pro(respond))
    async with Client(make_server()) as client:
        result = await client.call_tool(
            "jamf_update_computer",
            {
                "computer_id": 42,
                "name": "Renamed Mac",
                "building_id": 7,
                "extension_attributes": [{"id": 9, "value": 123}],
            },
        )

    assert not result.is_error
    assert result.structured_content["data"]["updated_fields"] == [
        "general",
        "userAndLocation",
        "extensionAttributes",
    ]
    assert len(requests) == 1
    assert requests[0].method == "PATCH"
    assert requests[0].url.path == "/api/v1/computers-inventory-detail/42"
    assert json.loads(requests[0].content) == {
        "general": {"name": "Renamed Mac"},
        "userAndLocation": {"buildingId": "7"},
        "extensionAttributes": [{"definitionId": "9", "values": ["123"]}],
    }


async def test_create_printer_posts_classic_xml_payload(
    mocked_clients: MockedClients,
) -> None:
    """Encode a printer create request as Classic API XML."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"printer": {"id": 51}})

    set_client(mocked_clients.jamf_pro(respond))
    async with Client(make_server()) as client:
        result = await client.call_tool(
            "jamf_create_printer",
            {"name": "Floor 2", "uri": "lpd://printer.example.test/", "make_default": True},
        )

    assert not result.is_error
    assert result.structured_content["data"] == {"printer": {"id": 51}}
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == "/JSSResource/printers/id/0"
    assert request.headers["content-type"] == "application/xml"
    printer = ET.fromstring(request.content)
    assert printer.tag == "printer"
    assert printer.findtext("name") == "Floor 2"
    assert printer.findtext("uri") == "lpd://printer.example.test/"
    assert printer.findtext("make_default") == "true"


async def test_override_risk_puts_device_ids_and_normalized_values(
    mocked_clients: MockedClients,
) -> None:
    """Send a normalized risk override to the Security Cloud endpoint."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"updated": 2})

    set_security_client(mocked_clients.security(respond))
    async with Client(make_server()) as client:
        result = await client.call_tool(
            "jamf_override_device_risk",
            {"device_ids": ["d-1", "d-2"], "risk": "high", "source": "wandera"},
        )

    assert not result.is_error
    assert result.structured_content["data"] == {"updated": 2}
    assert len(requests) == 1
    assert requests[0].method == "PUT"
    assert requests[0].url.path == "/risk/v1/override"
    assert json.loads(requests[0].content) == {
        "deviceIds": ["d-1", "d-2"],
        "risk": "HIGH",
        "source": "WANDERA",
    }


async def test_category_http_failure_preserves_status_and_details(
    mocked_clients: MockedClients,
) -> None:
    """Expose Jamf Pro error status and JSON body through MCP."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(409, json={"message": "Category already exists"})

    set_client(mocked_clients.jamf_pro(respond))
    async with Client(make_server()) as client:
        result = await client.call_tool("jamf_create_category", {"name": "Security"})

    assert result.is_error
    assert result.structured_content["status_code"] == 409
    assert result.structured_content["details"] == {"message": "Category already exists"}
    assert len(requests) == 1


async def test_protect_graphql_error_is_reported_by_tool(
    mocked_clients: MockedClients,
) -> None:
    """Preserve GraphQL errors returned with a successful HTTP status."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"errors": [{"message": "Alert access denied"}], "data": {"getAlert": None}},
        )

    set_protect_client(mocked_clients.protect(respond))
    async with Client(make_server()) as client:
        result = await client.call_tool("jamf_protect_get_alert", {"uuid": "alert-7"})

    assert result.is_error
    assert result.structured_content["graphql_errors"] == [{"message": "Alert access denied"}]
    assert len(requests) == 1


async def test_invalid_risk_override_does_not_call_upstream(
    mocked_clients: MockedClients,
) -> None:
    """Reject an unsupported risk value before sending any HTTP request."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    set_security_client(mocked_clients.security(respond))
    async with Client(make_server()) as client:
        result = await client.call_tool(
            "jamf_override_device_risk", {"device_ids": ["d-1"], "risk": "UNKNOWN"}
        )

    assert result.is_error
    assert "Invalid risk level" in result.structured_content["error"]
    assert requests == []


@pytest.mark.parametrize(
    "arguments",
    [
        {"api_version": "v3"},
        {"page": -1},
        {"page_size": 0},
        {"page_size": 101},
    ],
)
async def test_invalid_risk_read_arguments_do_not_call_upstream(
    mocked_clients: MockedClients,
    arguments: dict[str, object],
) -> None:
    """Reject invalid version and pagination values before making an HTTP request."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"records": []})

    set_security_client(mocked_clients.security(respond))
    async with Client(make_server()) as client:
        result = await client.call_tool("jamf_get_risk_devices", arguments)

    assert result.is_error
    assert "error" in result.structured_content
    assert requests == []


@pytest.mark.parametrize(
    ("tool_name", "argument_name"),
    [
        ("jamf_get_app_installer_deployments", "deployment_id"),
        ("jamf_get_app_installers", "app_id"),
    ],
)
@pytest.mark.parametrize(
    "deployment_id",
    [
        ".",
        "..",
        "foo#fragment",
        "1%252f..%252fcomputers",
        "１",
        "a b",
        "1\\..\\computers",
        "../computers",
        "../../../../JSSResource/accounts",
        "1/../computers",
        "1%2F..%2Fcomputers",
        "1%2e%2e%2fcomputers",
        "1?foo=bar",
        "1%3Ffoo=bar",
    ],
)
async def test_app_installer_deployment_id_rejects_invalid_input_before_request(
    mocked_clients: MockedClients,
    tool_name: str,
    argument_name: str,
    deployment_id: str,
) -> None:
    """Reject invalid identifiers through MCP without making an HTTP request."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    set_client(mocked_clients.jamf_pro(respond))
    async with Client(make_server()) as client:
        result = await client.call_tool(tool_name, {argument_name: deployment_id})

    assert result.is_error
    assert "single safe ASCII identifier" in result.structured_content["error"]
    assert requests == []


@pytest.mark.parametrize(
    ("tool_name", "argument_name"),
    [
        ("jamf_get_app_installer_deployments", "deployment_id"),
        ("jamf_get_app_installers", "app_id"),
    ],
)
@pytest.mark.parametrize("deployment_id", ["42", "deployment-42", "0", "abc.1_~"])
async def test_app_installer_deployment_id_preserves_valid_path(
    mocked_clients: MockedClients,
    tool_name: str,
    argument_name: str,
    deployment_id: str,
) -> None:
    """Keep a valid opaque deployment ID on the expected Jamf Pro v1 endpoint."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": deployment_id, "name": "Firefox"})

    set_client(mocked_clients.jamf_pro(respond))
    async with Client(make_server()) as client:
        result = await client.call_tool(tool_name, {argument_name: deployment_id})

    assert not result.is_error
    assert result.structured_content["data"] == {"id": deployment_id, "name": "Firefox"}
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == f"/api/v1/app-installers/deployments/{deployment_id}"


async def test_security_http_failure_preserves_status_and_body(
    mocked_clients: MockedClients,
) -> None:
    """Expose an upstream RISK API failure without losing its response body."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(403, json={"reason": "insufficient_scope"})

    set_security_client(mocked_clients.security(respond))
    async with Client(make_server()) as client:
        result = await client.call_tool("jamf_get_risk_devices", {"page": 1})

    assert result.is_error
    assert result.structured_content["status_code"] == 403
    assert result.structured_content["details"] == {"reason": "insufficient_scope"}
    assert len(requests) == 1


@pytest.mark.parametrize(
    ("tool_name", "argument_name", "path"),
    [
        (
            "jamf_get_app_installer_deployments",
            "deployment_id",
            "/api/v1/app-installers/deployments",
        ),
        ("jamf_get_app_installers", "app_id", "/api/v1/app-installers/titles"),
    ],
)
async def test_empty_app_installer_identifier_preserves_list_behavior(
    mocked_clients: MockedClients,
    tool_name: str,
    argument_name: str,
    path: str,
) -> None:
    """An empty optional identifier retains the original collection lookup."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": []})

    set_client(mocked_clients.jamf_pro(respond))
    async with Client(make_server()) as client:
        result = await client.call_tool(tool_name, {argument_name: ""})
    assert not result.is_error
    assert len(requests) == 1
    assert requests[0].url.path == path
