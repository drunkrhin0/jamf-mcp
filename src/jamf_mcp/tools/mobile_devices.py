# Copyright 2026, Jamf Software LLC
"""Mobile device management tools for Jamf Pro.

This module provides tools for retrieving and updating iOS, iPadOS,
and tvOS device inventory information.
"""

import logging
from typing import Optional, Union

from ..client import JamfAPIError
from ._common import format_error, format_response, get_client_safe
from ._registry import jamf_tool

logger = logging.getLogger(__name__)


@jamf_tool(read_only=True)
async def jamf_get_mobile_device(
    device_id: Optional[int] = None,
    serial_number: Optional[str] = None,
    name: Optional[str] = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get mobile device information from Jamf Pro.

    Retrieves detailed information for iOS, iPadOS, and tvOS devices managed by
    Jamf Pro. Includes hardware details, installed apps, and management status.

    Args:
        device_id: Jamf Pro mobile device ID for specific device
        serial_number: Device serial number for exact match search
        name: Device name to search for (supports partial matches)
        page: Page number for pagination (0-indexed, default: 0)
        page_size: Number of results per page (default: 100, max: 2000)

    Returns:
        JSON containing mobile device details or list of devices with hardware,
        network, and management information.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if device_id:
            result = await client.v2_get(f"mobile-devices/{device_id}/detail")
            return format_response(result, f"Retrieved mobile device ID {device_id}")

        params = {"page": page, "page-size": page_size}

        filters = []
        if serial_number:
            filters.append(f'serialNumber=="{serial_number}"')
        if name:
            filters.append(f'name=="{name}*"')
        if filters:
            params["filter"] = " and ".join(filters)

        result = await client.v2_get("mobile-devices", params=params)
        count = result.get("totalCount", len(result.get("results", [])))
        return format_response(result, f"Retrieved {count} mobile devices")

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting mobile device info")
        return format_error(e)


def _build_location_data(
    username: Optional[str],
    realname: Optional[str],
    email: Optional[str],
    department_id: Optional[Union[str, int]],
    building_id: Optional[Union[str, int]],
    room: Optional[str],
    phone: Optional[str],
    position: Optional[str],
) -> dict:
    """Build location data dict from provided fields."""
    location = {}
    field_mappings = [
        (username, "username"),
        (realname, "realName"),
        (email, "emailAddress"),
        (room, "room"),
        (phone, "phone"),
        (position, "position"),
    ]
    for value, key in field_mappings:
        if value is not None:
            location[key] = value

    # ID fields need string conversion
    if department_id is not None:
        location["departmentId"] = str(department_id)
    if building_id is not None:
        location["buildingId"] = str(building_id)

    return location


@jamf_tool
async def jamf_update_mobile_device(
    device_id: int,
    name: Optional[str] = None,
    asset_tag: Optional[str] = None,
    username: Optional[str] = None,
    realname: Optional[str] = None,
    email: Optional[str] = None,
    department_id: Optional[Union[str, int]] = None,
    building_id: Optional[Union[str, int]] = None,
    room: Optional[str] = None,
    phone: Optional[str] = None,
    position: Optional[str] = None,
) -> str:
    """Update mobile device information in Jamf Pro.

    Updates inventory fields for a specific mobile device. Only provided fields
    will be updated; omitted fields remain unchanged.

    Args:
        device_id: Jamf Pro mobile device ID to update (required)
        name: New device display name
        asset_tag: Asset tag value for inventory tracking
        username: Assigned user's username
        realname: Assigned user's full/display name
        email: Assigned user's email address
        department_id: Department ID (use jamf_get_departments to find valid IDs).
            Accepts integer or string, e.g., 1 or "1"
        building_id: Building ID (use jamf_get_buildings to find valid IDs).
            Accepts integer or string, e.g., 28 or "28"
        room: Room number or name (free-form text, no validation)
        phone: Contact phone number (free-form text)
        position: User's job position or title (free-form text)

    Returns:
        JSON with update confirmation and the updated device record.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        update_data = {}
        if name is not None:
            update_data["name"] = name
        if asset_tag is not None:
            update_data["assetTag"] = asset_tag

        location = _build_location_data(
            username, realname, email, department_id, building_id, room, phone, position
        )
        if location:
            update_data["location"] = location

        if not update_data:
            return format_error(ValueError("No update fields provided"))

        result = await client.v2_patch(f"mobile-devices/{device_id}", update_data)

        concise_result = {
            "id": device_id,
            "updated_fields": list(update_data.keys()),
        }
        if isinstance(result, dict):
            concise_result["name"] = result.get("name")
            concise_result["serialNumber"] = result.get("serialNumber")

        return format_response(concise_result, f"Updated mobile device ID {device_id}")

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error updating mobile device info")
        return format_error(e)
