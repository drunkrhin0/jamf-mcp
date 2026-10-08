# Copyright 2026, Jamf Software LLC
"""Category management tools for Jamf Pro.

This module provides tools for retrieving and creating categories used to
organize policies, configuration profiles, packages, and other Jamf Pro objects.
"""

import logging
from typing import Optional

from ..client import JamfAPIError
from ._common import format_error, format_response, get_client_safe
from ._registry import jamf_tool

logger = logging.getLogger(__name__)


@jamf_tool(read_only=True)
async def jamf_get_categories(
    category_id: Optional[int] = None,
    name: Optional[str] = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get categories from Jamf Pro.

    Retrieves categories used to organize Jamf Pro objects like policies,
    profiles, packages, and scripts. Categories help with organization
    and can be used in Self Service for grouping items.

    Args:
        category_id: Specific category ID to retrieve
        name: Filter categories by name (partial match)
        page: Page number for pagination (0-indexed, default: 0)
        page_size: Number of results per page (default: 100)

    Returns:
        JSON containing category list with names, IDs, and priority values.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if category_id:
            result = await client.v1_get(f"categories/{category_id}")
            return format_response(result, f"Retrieved category ID {category_id}")

        params = {"page": page, "page-size": page_size}
        if name:
            params["filter"] = f'name=="{name}*"'

        result = await client.v1_get("categories", params=params)
        count = result.get("totalCount", len(result.get("results", [])))
        return format_response(result, f"Retrieved {count} categories")

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting categories")
        return format_error(e)


@jamf_tool(destructive=False)
async def jamf_create_category(
    name: str,
    priority: int = 9,
) -> str:
    """Create a category in Jamf Pro.

    Creates a new category for organizing Jamf Pro objects. Categories can be
    assigned to policies, profiles, packages, scripts, and other items.

    Args:
        name: Category name (required, must be unique)
        priority: Priority level 1-20 (default: 9)
            Lower numbers = higher priority in Self Service display

    Returns:
        JSON with creation result including new category ID.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if not 1 <= priority <= 20:
            return format_error(ValueError("Priority must be between 1 and 20"))

        payload = {
            "name": name,
            "priority": priority,
        }

        result = await client.v1_post("categories", payload)
        return format_response(result, f"Created category '{name}'")

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error creating category")
        return format_error(e)
