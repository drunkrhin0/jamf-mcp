# Copyright 2026, Jamf Software LLC
"""Script management tools for Jamf Pro.

This module provides tools for retrieving scripts that can be executed
on managed computers via policies or other deployment methods.
"""

import logging
from typing import Optional

from ..client import JamfAPIError
from ._common import format_error, format_response, get_client_safe
from ._registry import jamf_tool

logger = logging.getLogger(__name__)


@jamf_tool(read_only=True)
async def jamf_get_scripts(
    script_id: Optional[int] = None,
    name: Optional[str] = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get scripts from Jamf Pro.

    Retrieves scripts that can be executed on managed computers via policies.
    Scripts can run shell commands, install software, configure settings, etc.

    Args:
        script_id: Specific script ID to retrieve full script contents
        name: Filter scripts by name (partial match)
        page: Page number for pagination (0-indexed, default: 0)
        page_size: Number of results per page (default: 100)

    Returns:
        JSON containing script list or full script details including contents,
        parameters, and execution settings.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if script_id:
            result = await client.v1_get(f"scripts/{script_id}")
            return format_response(result, f"Retrieved script ID {script_id}")

        params = {"page": page, "page-size": page_size}
        if name:
            params["filter"] = f'name=="{name}*"'

        result = await client.v1_get("scripts", params=params)
        count = result.get("totalCount", len(result.get("results", [])))
        return format_response(result, f"Retrieved {count} scripts")

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting scripts")
        return format_error(e)
