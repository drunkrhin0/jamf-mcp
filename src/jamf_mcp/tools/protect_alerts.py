# Copyright 2026, Jamf Software LLC
"""Jamf Protect alert tools."""

import logging
from typing import Any

from ..protect_client import ProtectAPIError
from ._common import format_error, format_response, get_protect_client_safe
from ._registry import jamf_tool

logger = logging.getLogger(__name__)


def _filter_alerts(
    items: list[dict[str, Any]],
    severity: str | None,
    status: str | None,
) -> list[dict[str, Any]]:
    """Filter alerts by severity and/or status (case-insensitive)."""
    if not severity and not status:
        return items

    def matches(item: dict[str, Any]) -> bool:
        if severity and (item.get("severity") or "").lower() != severity.lower():
            return False
        if status and (item.get("status") or "").lower() != status.lower():
            return False
        return True

    return [item for item in items if matches(item)]


def _build_result_message(returned: int, filtered: int, total: int) -> str:
    """Build result message with optional filtering/limiting info."""
    msg = f"Retrieved {returned} alerts"
    if filtered > returned:
        msg += f" (limited from {filtered})"
    if total != filtered:
        msg += f" (filtered from {total} total)"
    return msg


# Jamf Protect GraphQL query.
GET_ALERT_QUERY = """
query getAlert($uuid: ID!) {
  getAlert(uuid: $uuid) {
    json
    computer {
      uuid
    }
    severity
    status
    eventType
  }
}
"""

# List query - listAlerts requires AlertQueryInput (all fields optional)
LIST_ALERTS_QUERY = """
query listAlerts($input: AlertQueryInput!) {
  listAlerts(input: $input) {
    items {
      uuid
      severity
      status
      eventType
      created
      computer {
        uuid
        hostName
      }
    }
  }
}
"""


@jamf_tool(read_only=True)
async def jamf_protect_get_alert(uuid: str) -> str:
    """Get a specific security alert from Jamf Protect by UUID.

    Retrieves detailed information about a security alert including the full
    JSON payload, severity, status, event type, and associated computer.

    Args:
        uuid: The UUID of the alert to retrieve (required)

    Returns:
        JSON containing the alert details including:
        - json: Full alert JSON payload with detailed event data
        - severity: Alert severity level
        - status: Alert status (e.g., New, InProgress, Resolved)
        - eventType: Type of security event
        - computer: Associated computer UUID
    """
    client, error = get_protect_client_safe()
    if error:
        return error

    try:
        result = await client.query(GET_ALERT_QUERY, variables={"uuid": uuid})
        alert = result.get("getAlert")

        if not alert:
            return format_error(ValueError(f"Alert not found: {uuid}"))

        return format_response(alert, f"Retrieved alert {uuid}")

    except ProtectAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting Protect alert")
        return format_error(e)


@jamf_tool(read_only=True)
async def jamf_protect_list_alerts(
    severity: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> str:
    """List security alerts from Jamf Protect.

    Retrieves a list of security alerts. Client-side filtering by severity
    and status is available. Results are limited to control response size.

    Note: Filtering and limiting are performed client-side after fetching alerts.
    The full JSON payload for each alert is NOT included in list results -
    use jamf_protect_get_alert with a specific UUID to get full details.

    Args:
        severity: Filter by severity (e.g., Low, Medium, High, Critical)
        status: Filter by status (e.g., New, InProgress, Resolved)
        limit: Maximum number of alerts to return (default: 100)

    Returns:
        JSON containing a list of alerts with:
        - uuid: Alert UUID (use with jamf_protect_get_alert for full details)
        - severity: Alert severity level
        - status: Alert status
        - eventType: Type of security event
        - created: When the alert was created
        - computer: Associated computer (uuid, hostName)
    """
    client, error = get_protect_client_safe()
    if error:
        return error

    try:
        result = await client.query(LIST_ALERTS_QUERY, variables={"input": {}})
        items = result.get("listAlerts", {}).get("items", [])
        total_count = len(items)

        # Apply client-side filtering
        items = _filter_alerts(items, severity, status)
        filtered_count = len(items)

        # Apply limit
        if limit and len(items) > limit:
            items = items[:limit]

        msg = _build_result_message(len(items), filtered_count, total_count)
        return format_response({"items": items}, msg)

    except ProtectAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error listing Protect alerts")
        return format_error(e)
