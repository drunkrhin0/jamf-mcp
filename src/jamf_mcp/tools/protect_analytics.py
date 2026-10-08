# Copyright 2026, Jamf Software LLC
"""Jamf Protect analytics tools."""

import logging

from ..protect_client import ProtectAPIError
from ._common import format_error, format_response, get_protect_client_safe
from ._registry import jamf_tool

logger = logging.getLogger(__name__)


GET_ANALYTIC_QUERY = """
query GetAnalytic($uuid: ID!) {
  getAnalytic(uuid: $uuid) {
    uuid
    name
    description
    severity
    inputType
    filter
  }
}
"""

LIST_ANALYTICS_QUERY = """
query ListAnalytics {
  listAnalytics {
    items {
      uuid
      name
      description
      severity
      created
      updated
    }
  }
}
"""


@jamf_tool(read_only=True)
async def jamf_protect_get_analytic(uuid: str) -> str:
    """Get a specific analytic rule from Jamf Protect by UUID.

    Retrieves detailed information about an analytics rule including its
    detection criteria, severity, and filter configuration.

    Args:
        uuid: The UUID of the analytic to retrieve (required)

    Returns:
        JSON containing the analytic details including:
        - uuid: Analytic UUID
        - name: Analytic name
        - description: Human-readable description
        - severity: Alert severity when triggered (LOW, MEDIUM, HIGH, CRITICAL)
        - inputType: Type of data the analytic monitors
        - filter: Detection filter/criteria
    """
    client, error = get_protect_client_safe()
    if error:
        return error

    try:
        result = await client.query(GET_ANALYTIC_QUERY, variables={"uuid": uuid})
        analytic = result.get("getAnalytic")

        if not analytic:
            return format_error(ValueError(f"Analytic not found: {uuid}"))

        return format_response(analytic, f"Retrieved analytic {uuid}")

    except ProtectAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting Protect analytic")
        return format_error(e)


@jamf_tool(read_only=True)
async def jamf_protect_list_analytics() -> str:
    """List all analytics rules configured in Jamf Protect.

    Retrieves a list of all analytics (detection rules) configured in the
    Jamf Protect tenant. Analytics define what security events to detect
    and how to generate alerts.

    Returns:
        JSON containing a list of analytics with:
        - uuid: Analytic UUID
        - name: Analytic name
        - description: Human-readable description
        - severity: Alert severity when triggered
        - created: When the analytic was created
        - updated: When the analytic was last modified
    """
    client, error = get_protect_client_safe()
    if error:
        return error

    try:
        result = await client.query(LIST_ANALYTICS_QUERY)
        analytics_data = result.get("listAnalytics", {})
        items = analytics_data.get("items", [])

        return format_response(analytics_data, f"Retrieved {len(items)} analytics")

    except ProtectAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error listing Protect analytics")
        return format_error(e)
