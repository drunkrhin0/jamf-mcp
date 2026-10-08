# Copyright 2026, Jamf Software LLC
"""PreStage enrollment management tools for Jamf Pro.

This module provides tools for retrieving PreStage Enrollments which define
the automated enrollment configuration for devices enrolling via Apple
Business Manager (ABM) or Apple School Manager (ASM).
"""

import logging
from typing import Optional

from ..client import JamfAPIError
from ._common import format_error, format_response, get_client_safe
from ._registry import jamf_tool

logger = logging.getLogger(__name__)


@jamf_tool(read_only=True)
async def jamf_get_prestages(
    prestage_type: str = "computer",
    prestage_id: Optional[int] = None,
    name: Optional[str] = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get PreStage Enrollments from Jamf Pro.

    Retrieves PreStage Enrollments which define automated enrollment settings
    for devices enrolled via Apple Business Manager (ABM) or Apple School Manager (ASM).
    PreStages control Setup Assistant options, authentication, naming, and initial config.

    Args:
        prestage_type: "computer" for macOS or "mobile_device" for iOS/iPadOS
        prestage_id: Specific prestage ID to retrieve full configuration
        name: Filter prestages by display name (partial match)
        page: Page number for pagination (0-indexed, default: 0)
        page_size: Number of results per page (default: 100)

    Returns:
        JSON containing prestage list or detailed configuration including
        assigned devices, authentication settings, and Setup Assistant options.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if prestage_type == "computer":
            endpoint = "computer-prestages"
            if prestage_id:
                result = await client.v3_get(f"{endpoint}/{prestage_id}")
                return format_response(result, f"Retrieved {prestage_type} prestage ID {prestage_id}")
            params = {"page": page, "page-size": page_size}
            result = await client.v3_get(endpoint, params=params)
        else:
            endpoint = "mobile-device-prestages"
            if prestage_id:
                result = await client.v2_get(f"{endpoint}/{prestage_id}")
                return format_response(result, f"Retrieved {prestage_type} prestage ID {prestage_id}")
            params = {"page": page, "page-size": page_size}
            result = await client.v2_get(endpoint, params=params)

        prestages = result.get("results", [])

        if name:
            prestages = [p for p in prestages if name.lower() in p.get("displayName", "").lower()]

        total_count = result.get("totalCount", len(prestages))

        return format_response(
            {"results": prestages, "totalCount": total_count},
            f"Retrieved {len(prestages)} {prestage_type} prestages (total: {total_count})"
        )

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting prestages")
        return format_error(e)
