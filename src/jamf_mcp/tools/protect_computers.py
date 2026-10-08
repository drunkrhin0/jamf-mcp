# Copyright 2026, Jamf Software LLC
"""Jamf Protect computer tools."""

import logging
from typing import Any

from ..protect_client import ProtectAPIError
from ._common import format_error, format_response, get_protect_client_safe
from ._registry import jamf_tool

logger = logging.getLogger(__name__)


def _filter_computers(
    items: list[dict[str, Any]],
    hostname: str | None,
    serial: str | None,
) -> list[dict[str, Any]]:
    """Filter computers by hostname and/or serial (case-insensitive partial match)."""
    if not hostname and not serial:
        return items

    def matches(item: dict[str, Any]) -> bool:
        if hostname and hostname.lower() not in (item.get("hostName") or "").lower():
            return False
        if serial and serial.lower() not in (item.get("serial") or "").lower():
            return False
        return True

    return [item for item in items if matches(item)]


def _build_result_message(returned: int, filtered: int, total: int) -> str:
    """Build result message with optional filtering/limiting info."""
    msg = f"Retrieved {returned} computers"
    if filtered > returned:
        msg += f" (limited from {filtered})"
    if total != filtered:
        msg += f" (filtered from {total} total)"
    return msg


# Jamf Protect GraphQL query.
GET_COMPUTER_QUERY = """
query getComputer($uuid: ID!) {
  getComputer(uuid: $uuid) {
    hostName
    serial
    modelName
    osString
    version
    plan {
      name
    }
  }
}
"""

# Simple list query without input types (matching listAnalytics pattern)
LIST_COMPUTERS_QUERY = """
query listComputers {
  listComputers {
    items {
      uuid
      hostName
      serial
      modelName
      osString
    }
  }
}
"""


@jamf_tool(read_only=True)
async def jamf_protect_get_computer(uuid: str) -> str:
    """Get a specific computer from Jamf Protect by UUID.

    Retrieves detailed information about a computer enrolled in Jamf Protect,
    including hardware details, OS version, and the assigned protection plan.

    Args:
        uuid: The UUID of the computer to retrieve (required)

    Returns:
        JSON containing the computer details including:
        - hostName: Computer hostname
        - serial: Hardware serial number
        - modelName: Mac model name
        - osString: Full OS version string
        - version: Protect agent version
        - plan: Assigned protection plan name
    """
    client, error = get_protect_client_safe()
    if error:
        return error

    try:
        result = await client.query(GET_COMPUTER_QUERY, variables={"uuid": uuid})
        computer = result.get("getComputer")

        if not computer:
            return format_error(ValueError(f"Computer not found: {uuid}"))

        return format_response(computer, f"Retrieved computer {uuid}")

    except ProtectAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting Protect computer")
        return format_error(e)


@jamf_tool(read_only=True)
async def jamf_protect_list_computers(
    hostname: str | None = None,
    serial: str | None = None,
    limit: int = 100,
) -> str:
    """List computers enrolled in Jamf Protect.

    Retrieves a list of all computers enrolled in Jamf Protect.
    Client-side filtering by hostname or serial is available.

    Note: Filtering and limiting are performed client-side after fetching all computers.
    For large deployments, consider using jamf_protect_get_computer with
    a specific UUID instead.

    Args:
        hostname: Filter results by hostname (case-insensitive partial match)
        serial: Filter results by serial number (case-insensitive partial match)
        limit: Maximum number of computers to return (default: 100)

    Returns:
        JSON containing a list of computers with:
        - uuid: Computer UUID (use with jamf_protect_get_computer for details)
        - hostName: Computer hostname
        - serial: Hardware serial number
        - modelName: Mac model name
        - osString: Full OS version string
    """
    client, error = get_protect_client_safe()
    if error:
        return error

    try:
        result = await client.query(LIST_COMPUTERS_QUERY)
        items = result.get("listComputers", {}).get("items", [])
        total_count = len(items)

        # Apply client-side filtering
        items = _filter_computers(items, hostname, serial)
        filtered_count = len(items)

        # Apply limit
        if limit and len(items) > limit:
            items = items[:limit]

        msg = _build_result_message(len(items), filtered_count, total_count)
        return format_response({"items": items}, msg)

    except ProtectAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error listing Protect computers")
        return format_error(e)
