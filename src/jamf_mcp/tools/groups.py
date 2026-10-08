# Copyright 2026, Jamf Software LLC
"""Group management tools for Jamf Pro.

This module provides tools for retrieving and creating smart groups
(dynamic criteria-based) and static groups (manually-assigned devices).
"""

import logging
from typing import Optional

from ..client import JamfAPIError
from ._common import format_error, format_response, get_client_safe
from ._registry import jamf_tool

logger = logging.getLogger(__name__)


# =============================================================================
# Smart Groups
# =============================================================================

VALID_SEARCH_TYPES = {
    "is", "is not", "like", "not like", "has", "does not have",
    "greater than", "less than", "greater than or equal", "less than or equal",
    "matches regex", "does not match regex", "member of", "not member of"
}
VALID_CONJUNCTIONS = {"and", "or"}


def _validate_required_fields(index: int, criterion: dict) -> None:
    """Validate that required fields are present in a criterion."""
    if "name" not in criterion:
        raise ValueError(f"Criterion {index}: 'name' is required")
    if "search_type" not in criterion:
        raise ValueError(f"Criterion {index}: 'search_type' is required")
    if "value" not in criterion:
        raise ValueError(f"Criterion {index}: 'value' is required (use empty string for match-all)")


def _validate_search_type(index: int, search_type: str) -> None:
    """Validate that search_type is valid."""
    if search_type not in VALID_SEARCH_TYPES:
        raise ValueError(
            f"Criterion {index}: invalid search_type '{search_type}'. "
            f"Valid options: {', '.join(sorted(VALID_SEARCH_TYPES))}"
        )


def _get_conjunction(
    index: int, criterion: dict, default_conjunction: str, warnings: list[str]
) -> str:
    """Determine the conjunction (and/or) for a criterion."""
    if index == 0:
        if "and_or" in criterion and criterion["and_or"] != "and":
            warnings.append(
                f"Criterion 0: and_or='{criterion['and_or']}' ignored (first criterion has no predecessor)"
            )
        return "and"

    if "and_or" not in criterion:
        warnings.append(
            f"Criterion {index}: and_or not specified, using default '{default_conjunction}'"
        )
        return default_conjunction

    and_or = criterion["and_or"].lower()
    if and_or not in VALID_CONJUNCTIONS:
        raise ValueError(f"Criterion {index}: invalid and_or '{and_or}'. Must be 'and' or 'or'")
    return and_or


def _format_criterion(index: int, criterion: dict, and_or: str, search_type: str) -> dict:
    """Format a single criterion for the API."""
    return {
        "name": criterion["name"],
        "priority": criterion.get("priority", index),
        "and_or": and_or,
        "search_type": search_type,
        "value": str(criterion.get("value", "")),
        "opening_paren": criterion.get("opening_paren", False),
        "closing_paren": criterion.get("closing_paren", False),
    }


def _build_logic_string(index: int, formatted: dict, search_type: str) -> str:
    """Build a human-readable logic string for a criterion."""
    open_p = "(" if formatted["opening_paren"] else ""
    close_p = ")" if formatted["closing_paren"] else ""
    criterion_str = f'{formatted["name"]} {search_type} "{formatted["value"]}"'

    if index == 0:
        return f"{open_p}{criterion_str}{close_p}"
    return f"{formatted['and_or'].upper()} {open_p}{criterion_str}{close_p}"


def _check_mixed_conjunctions(formatted_criteria: list[dict], warnings: list[str]) -> None:
    """Warn if mixed AND/OR is used without parentheses."""
    if len(formatted_criteria) <= 1:
        return

    conjunctions_used = {c["and_or"] for c in formatted_criteria[1:]}
    has_mixed = len(conjunctions_used) > 1
    has_parens = any(c.get("opening_paren") or c.get("closing_paren") for c in formatted_criteria)

    if has_mixed and not has_parens:
        warnings.append(
            "Mixed AND/OR without parentheses may cause unexpected evaluation order. "
            "Consider using opening_paren/closing_paren to group criteria explicitly."
        )


def _validate_criteria(criteria: list[dict], default_conjunction: str) -> tuple[list[dict], list[str], str]:
    """Validate and normalize smart group criteria.

    Returns:
        Tuple of (formatted_criteria, warnings, logic_summary)
    """
    formatted_criteria = []
    warnings = []
    logic_parts = []

    for i, c in enumerate(criteria):
        _validate_required_fields(i, c)
        search_type = c.get("search_type", "is").lower()
        _validate_search_type(i, search_type)

        and_or = _get_conjunction(i, c, default_conjunction, warnings)
        formatted = _format_criterion(i, c, and_or, search_type)
        formatted_criteria.append(formatted)
        logic_parts.append(_build_logic_string(i, formatted, search_type))

    _check_mixed_conjunctions(formatted_criteria, warnings)
    logic_summary = " ".join(logic_parts)

    return formatted_criteria, warnings, logic_summary


@jamf_tool(read_only=True)
async def jamf_get_smart_groups(
    group_type: str = "computer",
    group_id: Optional[int] = None,
    name: Optional[str] = None,
) -> str:
    """Get smart groups from Jamf Pro.

    Retrieves smart groups which automatically include devices based on criteria.
    Smart groups dynamically update membership when devices match their rules.

    Args:
        group_type: Type of group - "computer" for macOS or "mobile_device" for iOS/iPadOS
        group_id: Specific group ID to retrieve full criteria and membership
        name: Filter groups by name (partial match)

    Returns:
        JSON containing smart group list or detailed group configuration including
        criteria logic and current membership count.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        resource = "computergroups" if group_type == "computer" else "mobiledevicegroups"

        if group_id:
            result = await client.classic_get(resource, group_id)
            key = "computer_group" if group_type == "computer" else "mobile_device_group"
            return format_response(result.get(key, result), f"Retrieved smart group ID {group_id}")

        result = await client.classic_get(resource)
        key = "computer_groups" if group_type == "computer" else "mobile_device_groups"
        groups = result.get(key, [])

        smart_groups = [g for g in groups if g.get("is_smart", False)]
        if name:
            smart_groups = [g for g in smart_groups if name.lower() in g.get("name", "").lower()]

        return format_response(
            {"smart_groups": smart_groups, "count": len(smart_groups)},
            f"Retrieved {len(smart_groups)} smart groups"
        )

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting smart groups")
        return format_error(e)


@jamf_tool(destructive=False)
async def jamf_create_smart_group(
    name: str,
    group_type: str = "computer",
    criteria: list[dict] = None,
    site_id: int = -1,
    default_conjunction: str = "and",
) -> str:
    """Create a smart group in Jamf Pro.

    Creates a new smart group with dynamic membership based on criteria.
    Devices matching the criteria are automatically added to the group.

    IMPORTANT - Understanding and_or logic:
        - The first criterion's and_or is ALWAYS ignored by Jamf
        - Each subsequent criterion's and_or connects to the PREVIOUS criterion
        - If and_or is omitted, defaults to default_conjunction parameter
        - Use default_conjunction="or" for OR-chains

    Args:
        name: Name for the smart group (required)
        group_type: "computer" for macOS or "mobile_device" for iOS/iPadOS
        criteria: List of criteria dicts with keys:
            - name: Criterion name (REQUIRED - e.g., "UDID", "Operating System Version")
            - search_type: Comparison (REQUIRED - "is", "like", "greater than", etc.)
            - value: Value to match (REQUIRED - use "" with "like" to match all)
            - and_or: "and" or "or" (optional, uses default_conjunction)
            - opening_paren/closing_paren: Group criteria (optional, default: False)
        site_id: Site ID to assign group to (-1 for none)
        default_conjunction: Default "and"/"or" when not specified (default: "and")

    Available search_type options:
        "is", "is not", "like", "not like", "has", "does not have",
        "greater than", "less than", "greater than or equal", "less than or equal",
        "matches regex", "does not match regex", "member of", "not member of"

    Common criterion names for computers:
        General: UDID, Computer Name, Serial Number, Department, Building
        Hardware: Model, Model Identifier, Architecture Type, Total RAM MB
        OS: Operating System Version, Operating System Build
        Security: FileVault 2 Status, SIP Status, Gatekeeper Status
        Management: Last Inventory Update, Enrolled via DEP, User Approved MDM

    Returns:
        JSON with creation result including new group ID, logic summary, and any warnings.

    Example - Match all Macs:
        criteria=[{"name": "UDID", "value": "", "search_type": "like"}]

    Example - OR chain for Apple Silicon:
        criteria=[
            {"name": "Processor Type", "value": "M3", "search_type": "like"},
            {"name": "Processor Type", "value": "M4", "search_type": "like"}
        ],
        default_conjunction="or"
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if not criteria:
            return format_error(ValueError("At least one criterion is required for smart groups"))

        if default_conjunction.lower() not in ("and", "or"):
            return format_error(ValueError("default_conjunction must be 'and' or 'or'"))

        formatted_criteria, warnings, logic_summary = _validate_criteria(
            criteria, default_conjunction.lower()
        )

        if group_type == "computer":
            group_key = "computer_group"
            resource = "computergroups"
        else:
            group_key = "mobile_device_group"
            resource = "mobiledevicegroups"

        payload = {
            group_key: {
                "name": name,
                "is_smart": True,
                "site": {"id": site_id},
                "criteria": formatted_criteria,
            }
        }

        result = await client.classic_post(resource, payload)

        response_data = {
            "id": result.get("id"),
            "logic_summary": logic_summary,
            "criteria_count": len(formatted_criteria),
        }
        if warnings:
            response_data["warnings"] = warnings

        message = f"Created smart group '{name}'"
        if warnings:
            message += f" with {len(warnings)} warning(s)"

        return format_response(response_data, message)

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error creating smart group")
        return format_error(e)


# =============================================================================
# Static Groups
# =============================================================================


@jamf_tool(read_only=True)
async def jamf_get_static_groups(
    group_type: str = "computer",
    group_id: Optional[int] = None,
    name: Optional[str] = None,
) -> str:
    """Get static groups from Jamf Pro.

    Retrieves static groups which contain manually-assigned devices.
    Unlike smart groups, membership is explicitly managed.

    Args:
        group_type: "computer" for macOS or "mobile_device" for iOS/iPadOS
        group_id: Specific group ID to retrieve member list
        name: Filter groups by name (partial match)

    Returns:
        JSON containing static group list or detailed group with member devices.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        resource = "computergroups" if group_type == "computer" else "mobiledevicegroups"

        if group_id:
            result = await client.classic_get(resource, group_id)
            key = "computer_group" if group_type == "computer" else "mobile_device_group"
            return format_response(result.get(key, result), f"Retrieved static group ID {group_id}")

        result = await client.classic_get(resource)
        key = "computer_groups" if group_type == "computer" else "mobile_device_groups"
        groups = result.get(key, [])

        static_groups = [g for g in groups if not g.get("is_smart", True)]
        if name:
            static_groups = [g for g in static_groups if name.lower() in g.get("name", "").lower()]

        return format_response(
            {"static_groups": static_groups, "count": len(static_groups)},
            f"Retrieved {len(static_groups)} static groups"
        )

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting static groups")
        return format_error(e)


@jamf_tool(destructive=False)
async def jamf_create_static_group(
    name: str,
    group_type: str = "computer",
    device_ids: list[int] = None,
    site_id: int = -1,
) -> str:
    """Create a static group in Jamf Pro.

    Creates a new static group with optional initial device membership.
    Devices can be added or removed after creation.

    Args:
        name: Name for the static group (required)
        group_type: "computer" for macOS or "mobile_device" for iOS/iPadOS
        device_ids: List of device IDs to include initially (optional)
        site_id: Site ID to assign group to (-1 for none)

    Returns:
        JSON with creation result including new group ID.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if group_type == "computer":
            group_key = "computer_group"
            resource = "computergroups"
            members_key = "computers"
            member_key = "computer"
        else:
            group_key = "mobile_device_group"
            resource = "mobiledevicegroups"
            members_key = "mobile_devices"
            member_key = "mobile_device"

        members = []
        if device_ids:
            for device_id in device_ids:
                members.append({member_key: {"id": device_id}})

        payload = {
            group_key: {
                "name": name,
                "is_smart": False,
                "site": {"id": site_id},
                members_key: members,
            }
        }

        result = await client.classic_post(resource, payload)
        return format_response(result, f"Created static group '{name}' with {len(device_ids or [])} devices")

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error creating static group")
        return format_error(e)
