"""Direct Pro reporting through MCP, distinct from CIS benchmark reporting."""

import httpx
from backend_helpers import MockedClients, make_server
from mcp import Client

from jamf_mcp.tools._common import set_client


async def test_ddm_status_preserves_declaration_failures(mocked_clients: MockedClients) -> None:
    """Jamf's status-items contract uses management UUID and retains report values."""
    body = {
        "statusItems": [
            {
                "key": "management.declarations.configurations",
                "value": [
                    {
                        "identifier": "Blueprint_test",
                        "active": False,
                        "valid": "invalid",
                        "reasons": [{"description": "Invalid configuration"}],
                    }
                ],
                "lastUpdateTime": "2026-10-07T00:00:00Z",
            }
        ]
    }

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v1/ddm/11111111-1111-4111-8111-111111111111/status-items"
        return httpx.Response(200, json=body)

    set_client(mocked_clients.jamf_pro(respond))
    async with Client(make_server()) as client:
        result = await client.call_tool(
            "jamf_get_ddm_status",
            {
                "client_management_id": "11111111-1111-4111-8111-111111111111",
            },
        )
    assert not result.is_error
    assert result.structured_content["data"] == body


async def test_empty_conditional_access_report_is_not_a_cis_result(
    mocked_clients: MockedClients,
) -> None:
    """An empty Pro compliance array remains unknown, not a CIS pass/fail inference."""

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == (
            "/api/v1/conditional-access/device-compliance-information/computer/42"
        )
        return httpx.Response(200, json=[])

    set_client(mocked_clients.jamf_pro(respond))
    async with Client(make_server()) as client:
        result = await client.call_tool(
            "jamf_get_device_compliance_information",
            {
                "device_id": 42,
            },
        )
    assert not result.is_error
    assert result.structured_content["data"] == []
    assert result.structured_content["report_type"] == "conditional_access"
    assert result.structured_content["has_records"] is False
    assert "CIS" in result.structured_content["note"]


async def test_mobile_conditional_access_and_single_ddm_key(mocked_clients: MockedClients) -> None:
    """Documented mobile and single-status-item endpoints are available through MCP."""
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        if request.url.path.endswith("/mobile/12"):
            return httpx.Response(200, json=[{"complianceState": "NON_COMPLIANT"}])
        assert request.url.path.endswith("/status-items/management.declarations.configurations")
        return httpx.Response(
            200,
            json={
                "key": "management.declarations.configurations",
                "value": [{"active": False, "valid": "invalid"}],
            },
        )

    set_client(mocked_clients.jamf_pro(respond))
    async with Client(make_server()) as client:
        compliance = await client.call_tool(
            "jamf_get_device_compliance_information",
            {
                "device_id": 12,
                "device_type": "mobile",
            },
        )
        ddm = await client.call_tool(
            "jamf_get_ddm_status",
            {
                "client_management_id": "11111111-1111-4111-8111-111111111111",
                "key": "management.declarations.configurations",
            },
        )
    assert not compliance.is_error and not ddm.is_error
    assert compliance.structured_content["has_records"] is True
    assert compliance.structured_content["data"] == [{"complianceState": "NON_COMPLIANT"}]
    assert ddm.structured_content["data"]["value"] == [{"active": False, "valid": "invalid"}]
    assert len(requests) == 2


async def test_invalid_identifiers_do_not_send_reporting_reads(
    mocked_clients: MockedClients,
) -> None:
    """Invalid IDs and dot segments fail before a reporting request is sent."""
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[])

    set_client(mocked_clients.jamf_pro(respond))
    async with Client(make_server()) as client:
        for name, arguments in [
            ("jamf_get_device_compliance_information", {"device_id": 0}),
            ("jamf_get_ddm_status", {"client_management_id": ".."}),
            ("jamf_get_ddm_status", {"client_management_id": "test", "key": ".."}),
        ]:
            result = await client.call_tool(name, arguments)
            assert result.is_error
    assert requests == []


async def test_ddm_privilege_failure_stays_an_mcp_error(mocked_clients: MockedClients) -> None:
    """A missing read privilege is not reported as a successful empty DDM report."""

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"errors": [{"code": "INVALID_PRIVILEGE"}]})

    set_client(mocked_clients.jamf_pro(respond))
    async with Client(make_server()) as client:
        result = await client.call_tool(
            "jamf_get_ddm_status",
            {
                "client_management_id": "11111111-1111-4111-8111-111111111111",
            },
        )
    assert result.is_error
    assert result.structured_content["status_code"] == 403
    assert result.structured_content["details"]["errors"][0]["code"] == "INVALID_PRIVILEGE"
