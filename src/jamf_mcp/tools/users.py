# Copyright 2026, Jamf Software LLC
"""User management tools for Jamf Pro.

This module provides tools for retrieving and updating user records
in Jamf Pro.
"""

import logging
from typing import Optional

from ..client import JamfAPIError
from ._common import format_error, format_response, get_client_safe
from ._registry import jamf_tool

logger = logging.getLogger(__name__)


@jamf_tool(read_only=True)
async def jamf_get_user(
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    email: Optional[str] = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get user information from Jamf Pro.

    Retrieves user records from Jamf Pro. Users represent the people assigned to
    devices and can be local Jamf Pro users or synced from LDAP/directory services.

    Args:
        user_id: Jamf Pro user ID for specific user details
        username: Username to search for (partial match)
        email: Email address to search for (partial match)
        page: Page number for pagination (0-indexed, default: 0)
        page_size: Number of results per page (default: 100)

    Returns:
        JSON containing user details including name, contact info, and linked devices.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if user_id:
            result = await client.classic_get("users", user_id)
            return format_response(result, f"Retrieved user ID {user_id}")

        result = await client.classic_get("users")

        users = result.get("users", [])
        if username:
            users = [u for u in users if username.lower() in u.get("name", "").lower()]
        if email:
            users = [u for u in users if email.lower() in u.get("email", "").lower()]

        start = page * page_size
        end = start + page_size
        paginated = users[start:end]

        return format_response(
            {"users": paginated, "totalCount": len(users)},
            f"Retrieved {len(paginated)} users (total: {len(users)})"
        )

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting user info")
        return format_error(e)


@jamf_tool
async def jamf_update_user(
    user_id: int,
    name: Optional[str] = None,
    full_name: Optional[str] = None,
    email: Optional[str] = None,
    phone_number: Optional[str] = None,
    position: Optional[str] = None,
) -> str:
    """Update user information in Jamf Pro.

    Updates a user record in Jamf Pro. Only provided fields will be updated.

    Args:
        user_id: Jamf Pro user ID to update (required)
        name: Username (login name)
        full_name: User's full display name
        email: Email address
        phone_number: Contact phone number
        position: Job position or title

    Returns:
        JSON with update confirmation.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        user_data = {}
        if name is not None:
            user_data["name"] = name
        if full_name is not None:
            user_data["full_name"] = full_name
        if email is not None:
            user_data["email"] = email
        if phone_number is not None:
            user_data["phone_number"] = phone_number
        if position is not None:
            user_data["position"] = position

        if not user_data:
            return format_error(ValueError("No update fields provided"))

        update_payload = {"user": user_data}
        result = await client.classic_put("users", user_id, update_payload)

        # Return a concise response
        concise_result = {
            "id": user_id,
            "updated_fields": list(user_data.keys()),
        }
        if isinstance(result, dict):
            concise_result["name"] = result.get("name")

        return format_response(concise_result, f"Updated user ID {user_id}")

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error updating user info")
        return format_error(e)
