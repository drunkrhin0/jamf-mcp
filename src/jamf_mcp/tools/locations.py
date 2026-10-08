# Copyright 2026, Jamf Software LLC
"""Location management tools for Jamf Pro.

This module provides tools for retrieving buildings and departments
from Jamf Pro. These are used for organizing devices and users by
physical location and organizational structure.
"""

import logging
from typing import Optional

from ..client import JamfAPIError
from ._common import format_error, format_response, get_client_safe
from ._registry import jamf_tool

logger = logging.getLogger(__name__)


@jamf_tool(read_only=True)
async def jamf_get_buildings(
    building_id: Optional[int] = None,
    name: Optional[str] = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get buildings from Jamf Pro.

    Retrieves building records from Jamf Pro. Buildings represent physical
    locations that can be assigned to computers, mobile devices, and users.
    These are useful for organizing devices by office location.

    Args:
        building_id: Specific building ID to retrieve full details
        name: Filter buildings by name (partial match, case-insensitive)
        page: Page number for pagination (0-indexed, default: 0)
        page_size: Number of results per page (default: 100)

    Returns:
        JSON containing building list with names and IDs, or detailed info
        for a specific building including any configured street address.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if building_id:
            result = await client.classic_get("buildings", building_id)
            return format_response(result, f"Retrieved building ID {building_id}")

        result = await client.classic_get("buildings")

        buildings = result.get("buildings", [])
        if name:
            buildings = [
                b for b in buildings if name.lower() in b.get("name", "").lower()
            ]

        start = page * page_size
        end = start + page_size
        paginated = buildings[start:end]

        return format_response(
            {"buildings": paginated, "totalCount": len(buildings)},
            f"Retrieved {len(paginated)} buildings (total: {len(buildings)})",
        )

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting buildings")
        return format_error(e)


@jamf_tool(read_only=True)
async def jamf_get_departments(
    department_id: Optional[int] = None,
    name: Optional[str] = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get departments from Jamf Pro.

    Retrieves department records from Jamf Pro. Departments represent
    organizational units that can be assigned to computers, mobile devices,
    and users. These are useful for organizing devices by team or business unit.

    Args:
        department_id: Specific department ID to retrieve full details
        name: Filter departments by name (partial match, case-insensitive)
        page: Page number for pagination (0-indexed, default: 0)
        page_size: Number of results per page (default: 100)

    Returns:
        JSON containing department list with names and IDs, or detailed info
        for a specific department.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if department_id:
            result = await client.classic_get("departments", department_id)
            return format_response(result, f"Retrieved department ID {department_id}")

        result = await client.classic_get("departments")

        departments = result.get("departments", [])
        if name:
            departments = [
                d for d in departments if name.lower() in d.get("name", "").lower()
            ]

        start = page * page_size
        end = start + page_size
        paginated = departments[start:end]

        return format_response(
            {"departments": paginated, "totalCount": len(departments)},
            f"Retrieved {len(paginated)} departments (total: {len(departments)})",
        )

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting departments")
        return format_error(e)
