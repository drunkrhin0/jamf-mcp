# Copyright 2026, Jamf Software LLC
"""Device risk management tools for Jamf Security Cloud.

This module provides tools for retrieving and managing device risk status
using the Jamf RISK API (part of Jamf Security Cloud).

Note: These tools require separate Jamf Security Cloud credentials
(JAMF_SECURITY_URL, JAMF_SECURITY_APP_ID, JAMF_SECURITY_APP_SECRET).
"""

import logging
from typing import Optional

from ..security_client import JamfSecurityAPIError
from ._common import format_error, format_response, get_security_client_safe
from ._registry import jamf_tool

logger = logging.getLogger(__name__)


@jamf_tool(read_only=True)
async def jamf_get_risk_devices(
    api_version: str = "v1",
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get device risk status from Jamf Security Cloud.

    Retrieves risk assessment information for devices managed by Jamf Security Cloud.
    This includes threat levels, compliance status, and risk scores.

    Note: Requires Jamf Security Cloud credentials to be configured:
    - JAMF_SECURITY_URL
    - JAMF_SECURITY_APP_ID
    - JAMF_SECURITY_APP_SECRET

    Args:
        api_version: Paginated API version, "v1" or "v2". Default: "v1".
        page: Page number for pagination (0-indexed, default: 0).
        page_size: Number of results per page (default: 100, maximum: 100).

    Returns:
        JSON containing device risk information including:
        - Device identifiers (ID, serial number, etc.)
        - Risk level (LOW, MEDIUM, HIGH, SEVERE)
        - Threat indicators and compliance status
        - Last assessment timestamp
    """
    client, error = get_security_client_safe()
    if error:
        return error

    if api_version not in {"v1", "v2"}:
        return format_error(ValueError("api_version must be v1 or v2"))
    if page < 0 or not 1 <= page_size <= 100:
        return format_error(ValueError("page must be non-negative and page_size must be 1 to 100"))

    try:
        if api_version == "v2":
            result = await client.get_risk_devices_v2(page=page, page_size=page_size)
            device_count = len(result.get("records", result.get("devices", result.get("results", []))))
            return format_response(result, f"Retrieved {device_count} devices with risk status (v2)")
        else:
            result = await client.get_risk_devices_v1(page=page, page_size=page_size)
            # v1 API returns devices in "records" with pagination info
            records = result.get("records", result.get("devices", result.get("results", [])))
            device_count = len(records)
            pagination = result.get("pagination", {})
            total = pagination.get("totalRecords", result.get("totalCount", device_count))
            return format_response(result, f"Retrieved {device_count} of {total} devices with risk status (v1)")

    except JamfSecurityAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting device risk status")
        return format_error(e)


@jamf_tool
async def jamf_override_device_risk(
    device_ids: list[str],
    risk: str,
    source: Optional[str] = None,
) -> str:
    """Override the risk level for specific devices in Jamf Security Cloud.

    Manually sets the risk level for one or more devices, overriding the
    automatically calculated risk assessment. Useful for marking devices
    as trusted after investigation or flagging devices with known issues.

    Note: Requires Jamf Security Cloud credentials to be configured:
    - JAMF_SECURITY_URL
    - JAMF_SECURITY_APP_ID
    - JAMF_SECURITY_APP_SECRET

    Args:
        device_ids: List of device IDs to override. Use jamf_get_risk_devices to
            find device IDs.
        risk: New risk level to set. Valid values:
            - "LOW" - Device is considered low risk
            - "MEDIUM" - Device has moderate risk indicators
            - "HIGH" - Device has significant risk indicators
            - "SEVERE" - Device is severely compromised or at risk
        source: Source of the override. Valid values:
            - "MANUAL" - Manual override by administrator (default)
            - "WANDERA" - Override from Jamf Security Cloud system

    Returns:
        JSON containing the override result with confirmation.
    """
    client, error = get_security_client_safe()
    if error:
        return error

    # Validate risk level
    valid_risk_levels = {"LOW", "MEDIUM", "HIGH", "SEVERE"}
    risk_upper = risk.upper()
    if risk_upper not in valid_risk_levels:
        return format_error(ValueError(
            f"Invalid risk level '{risk}'. Must be one of: {', '.join(sorted(valid_risk_levels))}"
        ))

    if not device_ids:
        return format_error(ValueError("At least one device ID is required"))

    # Validate source
    valid_sources = {"MANUAL", "WANDERA"}
    override_source = (source or "MANUAL").upper()
    if override_source not in valid_sources:
        return format_error(ValueError(
            f"Invalid source '{source}'. Must be one of: {', '.join(sorted(valid_sources))}"
        ))

    try:
        result = await client.override_device_risk(
            device_ids=device_ids,
            risk=risk_upper,
            source=override_source,
        )
        return format_response(
            result,
            f"Risk level set to {risk_upper} for {len(device_ids)} device(s)"
        )

    except JamfSecurityAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error overriding device risk")
        return format_error(e)
