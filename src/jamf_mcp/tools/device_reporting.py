"""Direct Pro device reporting, separate from Platform CIS benchmarks."""

import json
from typing import Literal
from urllib.parse import quote

from ._common import format_error, format_response, get_client_safe
from ._registry import jamf_tool


@jamf_tool(read_only=True)
async def jamf_get_ddm_status(client_management_id: str, key: str | None = None) -> str:
    """Read the latest DDM status report through the existing Jamf Pro client.

    Requires both Read Computers and Read Mobile Devices. client_management_id
    is general.managementId from Pro inventory, not the numeric computer ID or
    an assumed Platform device ID. Optional key selects one reported status item.
    Preserve declaration validity and failure reasons; successful retrieval alone
    does not prove every Blueprint is deployed or every CIS rule is passed.
    This tool never calls the DDM sync command and needs no Platform credentials.
    """
    client, error = get_client_safe()
    if error:
        return error
    try:
        identifiers = [client_management_id] + ([key] if key is not None else [])
        if any(not item.strip() or item in {".", ".."} for item in identifiers):
            raise ValueError("Management ID and optional key must be nonempty path identifiers")
        path = f"ddm/{quote(client_management_id, safe='')}/status-items"
        if key is not None:
            path += f"/{quote(key, safe='')}"
        return format_response(await client.v1_get(path), "Retrieved Pro DDM status report")
    except Exception as error:
        return format_error(error)


@jamf_tool(read_only=True)
async def jamf_get_device_compliance_information(
    device_id: int,
    device_type: Literal["computer", "mobile"] = "computer",
) -> str:
    """Read Pro conditional-access device compliance, not CIS benchmark results.

    Requires Read Device Compliance Information. Use a numeric Pro inventory ID
    and computer or mobile device type. These records relate to device-compliance
    integration, such as Microsoft Entra; empty results establish no compliance
    verdict. For CIS/NIST rule results, use jamf_platform_get_benchmark_rules and
    jamf_platform_get_benchmark_devices instead. Needs only existing Pro credentials.
    """
    client, error = get_client_safe()
    if error:
        return error
    try:
        if device_id < 1:
            raise ValueError("device_id must be a positive Pro inventory ID")
        data = await client.v1_get(
            f"conditional-access/device-compliance-information/{device_type}/{device_id}"
        )
        response = json.loads(format_response(data, "Retrieved conditional-access compliance"))
        response["report_type"] = "conditional_access"
        response["has_records"] = bool(data)
        response["note"] = (
            "This is not a CIS benchmark report. Empty records establish no compliance verdict. "
            "Use Platform benchmark rule and device reports for CIS/NIST results."
        )
        return json.dumps(response)
    except Exception as error:
        return format_error(error)
