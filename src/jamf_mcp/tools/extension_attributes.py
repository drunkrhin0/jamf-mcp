# Copyright 2026, Jamf Software LLC
"""Extension attribute management tools for Jamf Pro.

This module provides tools for retrieving and creating extension attributes
which define custom inventory fields for computers, mobile devices, and users.
"""

import logging
from typing import Optional

from ..client import JamfAPIError
from ._common import format_error, format_response, get_client_safe
from ._registry import jamf_tool

logger = logging.getLogger(__name__)


@jamf_tool(read_only=True)
async def jamf_get_extension_attributes(
    ea_type: str,
    ea_id: Optional[int] = None,
    name: Optional[str] = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get extension attributes from Jamf Pro.

    Retrieves extension attributes which define custom inventory fields.
    Extension attributes allow collecting additional device or user information
    beyond the standard inventory.

    Args:
        ea_type: Type of extension attribute (REQUIRED):
            - "computer" - Custom fields for macOS computers
            - "mobile_device" - Custom fields for iOS/iPadOS devices
            - "user" - Custom fields for Jamf Pro users
        ea_id: Specific extension attribute ID to retrieve full definition
        name: Filter by name (partial match)
        page: Page number for pagination (0-indexed, default: 0)
        page_size: Number of results per page (default: 100)

    Returns:
        JSON containing extension attribute list or detailed definition
        including input type, data type, and script contents (if applicable).
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if ea_type == "computer":
            if ea_id:
                result = await client.classic_get("computerextensionattributes", ea_id)
                return format_response(
                    result.get("computer_extension_attribute", result),
                    f"Retrieved computer extension attribute ID {ea_id}"
                )

            result = await client.classic_get("computerextensionattributes")
            eas = result.get("computer_extension_attributes", [])
        elif ea_type == "mobile_device":
            if ea_id:
                result = await client.classic_get("mobiledeviceextensionattributes", ea_id)
                return format_response(
                    result.get("mobile_device_extension_attribute", result),
                    f"Retrieved mobile device extension attribute ID {ea_id}"
                )

            result = await client.classic_get("mobiledeviceextensionattributes")
            eas = result.get("mobile_device_extension_attributes", [])
        elif ea_type == "user":
            if ea_id:
                result = await client.classic_get("userextensionattributes", ea_id)
                return format_response(
                    result.get("user_extension_attribute", result),
                    f"Retrieved user extension attribute ID {ea_id}"
                )

            result = await client.classic_get("userextensionattributes")
            eas = result.get("user_extension_attributes", [])
        else:
            return format_error(
                ValueError(f"Invalid ea_type '{ea_type}'. Must be 'computer', 'mobile_device', or 'user'")
            )

        if name:
            eas = [ea for ea in eas if name.lower() in ea.get("name", "").lower()]

        start = page * page_size
        end = start + page_size
        paginated = eas[start:end]

        return format_response(
            {"extension_attributes": paginated, "totalCount": len(eas)},
            f"Retrieved {len(paginated)} {ea_type} extension attributes (total: {len(eas)})"
        )

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting extension attributes")
        return format_error(e)


@jamf_tool(destructive=False)
async def jamf_create_extension_attribute(
    name: str,
    ea_type: str,
    data_type: str = "String",
    description: str = "",
    input_type: str = "Text Field",
    script_contents: Optional[str] = None,
    popup_choices: Optional[list[str]] = None,
    inventory_display: str = "Extension Attributes",
) -> str:
    """Create an extension attribute in Jamf Pro.

    Creates a new custom inventory field for computers, mobile devices, or users.
    Extension attributes extend the inventory data collected from devices.

    Args:
        name: Extension attribute name (required, must be unique)
        ea_type: Type (REQUIRED): "computer", "mobile_device", or "user"
        data_type: Data type for the value (default: "String"):
            - "String" - Text values
            - "Integer" - Numeric values
            - "Date" - Date values (YYYY-MM-DD format)
        description: Description shown in the Jamf Pro UI
        input_type: How values are collected (default: "Text Field"):
            - "Text Field" - Manual text entry
            - "Pop-up Menu" - Selection from predefined choices
            - "script" - Collected via script (computer only)
        script_contents: Script code (required if input_type is "script")
            Only valid for computer extension attributes
        popup_choices: List of choices (required if input_type is "Pop-up Menu")
        inventory_display: Display section in inventory (default: "Extension Attributes")

    Returns:
        JSON with creation result including new extension attribute ID.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        input_type_data = {"type": input_type}

        if input_type.lower() == "script" and script_contents:
            if ea_type != "computer":
                return format_error(
                    ValueError("Script input type is only valid for computer extension attributes")
                )
            input_type_data["script"] = script_contents
        elif input_type.lower() == "pop-up menu" and popup_choices:
            input_type_data["popup_choices"] = popup_choices

        if ea_type == "computer":
            resource = "computerextensionattributes"
            payload = {
                "computer_extension_attribute": {
                    "name": name,
                    "description": description,
                    "data_type": data_type,
                    "input_type": input_type_data,
                    "inventory_display": inventory_display,
                    "enabled": True,
                }
            }
        elif ea_type == "mobile_device":
            resource = "mobiledeviceextensionattributes"
            payload = {
                "mobile_device_extension_attribute": {
                    "name": name,
                    "description": description,
                    "data_type": data_type,
                    "input_type": input_type_data,
                    "inventory_display": inventory_display,
                }
            }
        elif ea_type == "user":
            resource = "userextensionattributes"
            payload = {
                "user_extension_attribute": {
                    "name": name,
                    "description": description,
                    "data_type": data_type,
                    "input_type": input_type_data,
                }
            }
        else:
            return format_error(
                ValueError(f"Invalid ea_type '{ea_type}'. Must be 'computer', 'mobile_device', or 'user'")
            )

        result = await client.classic_post(resource, payload)
        return format_response(result, f"Created {ea_type} extension attribute '{name}'")

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error creating extension attribute")
        return format_error(e)
