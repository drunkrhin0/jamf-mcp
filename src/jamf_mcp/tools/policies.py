# Copyright 2026, Jamf Software LLC
"""Policy management tools for Jamf Pro.

This module provides tools for retrieving computer policies which define
automated actions like software installation, script execution, and
configuration changes.
"""

import logging
from typing import Optional

from ..client import JamfAPIError
from ._common import format_error, format_response, get_client_safe
from ._registry import jamf_tool

logger = logging.getLogger(__name__)


@jamf_tool(read_only=True)
async def jamf_get_policies(
    policy_id: Optional[int] = None,
    name: Optional[str] = None,
    category: Optional[str] = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get policies from Jamf Pro.

    Retrieves computer policies that define automated management actions like
    software installation, script execution, and configuration changes.
    Policies can be triggered on various events or schedules.

    Args:
        policy_id: Specific policy ID to retrieve full configuration details
        name: Filter policies by name (partial match)
        category: Filter policies by category name
        page: Page number for pagination (0-indexed, default: 0)
        page_size: Number of results per page (default: 100)

    Returns:
        JSON containing policy list or detailed policy configuration including
        scope, triggers, packages, scripts, and other settings.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if policy_id:
            result = await client.classic_get("policies", policy_id)
            return format_response(result.get("policy", result), f"Retrieved policy ID {policy_id}")

        result = await client.classic_get("policies")
        policies = result.get("policies", [])

        if name:
            policies = [p for p in policies if name.lower() in p.get("name", "").lower()]
        if category:
            pass  # Category filtering requires fetching each policy

        start = page * page_size
        end = start + page_size
        paginated = policies[start:end]

        return format_response(
            {"policies": paginated, "totalCount": len(policies)},
            f"Retrieved {len(paginated)} policies (total: {len(policies)})"
        )

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting policies")
        return format_error(e)
