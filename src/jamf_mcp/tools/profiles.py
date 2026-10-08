# Copyright 2026, Jamf Software LLC
"""Configuration profile management tools for Jamf Pro.

This module provides tools for retrieving macOS and iOS/iPadOS/tvOS
configuration profiles.
"""

import logging
from typing import Optional

from ..client import JamfAPIError
from ._common import format_error, format_response, get_client_safe
from ._registry import jamf_tool

logger = logging.getLogger(__name__)


@jamf_tool(read_only=True)
async def jamf_get_computer_configuration_profiles(
    profile_id: Optional[int] = None,
    name: Optional[str] = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get computer configuration profiles from Jamf Pro.

    Retrieves macOS configuration profiles that define device settings, security
    configurations, restrictions, and other managed preferences delivered via MDM.

    Args:
        profile_id: Specific profile ID to retrieve full configuration and payloads
        name: Filter profiles by name (partial match)
        page: Page number for pagination (0-indexed, default: 0)
        page_size: Number of results per page (default: 100)

    Returns:
        JSON containing profile list or detailed profile configuration including
        scope, payloads, and deployment settings.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if profile_id:
            result = await client.classic_get("osxconfigurationprofiles", profile_id)
            return format_response(
                result.get("os_x_configuration_profile", result),
                f"Retrieved configuration profile ID {profile_id}"
            )

        result = await client.classic_get("osxconfigurationprofiles")
        profiles = result.get("os_x_configuration_profiles", [])

        if name:
            profiles = [p for p in profiles if name.lower() in p.get("name", "").lower()]

        start = page * page_size
        end = start + page_size
        paginated = profiles[start:end]

        return format_response(
            {"profiles": paginated, "totalCount": len(profiles)},
            f"Retrieved {len(paginated)} configuration profiles (total: {len(profiles)})"
        )

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting computer configuration profiles")
        return format_error(e)


@jamf_tool(read_only=True)
async def jamf_get_mobile_device_configuration_profiles(
    profile_id: Optional[int] = None,
    name: Optional[str] = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get mobile device configuration profiles from Jamf Pro.

    Retrieves iOS/iPadOS/tvOS configuration profiles that define device settings,
    restrictions, Wi-Fi, VPN, email, and other managed configurations.

    Args:
        profile_id: Specific profile ID to retrieve full configuration
        name: Filter profiles by name (partial match)
        page: Page number for pagination (0-indexed, default: 0)
        page_size: Number of results per page (default: 100)

    Returns:
        JSON containing profile list or detailed profile configuration including
        scope and payload settings.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if profile_id:
            result = await client.classic_get("mobiledeviceconfigurationprofiles", profile_id)
            return format_response(
                result.get("configuration_profile", result),
                f"Retrieved mobile device profile ID {profile_id}"
            )

        result = await client.classic_get("mobiledeviceconfigurationprofiles")
        profiles = result.get("configuration_profiles", [])

        if name:
            profiles = [p for p in profiles if name.lower() in p.get("name", "").lower()]

        start = page * page_size
        end = start + page_size
        paginated = profiles[start:end]

        return format_response(
            {"profiles": paginated, "totalCount": len(profiles)},
            f"Retrieved {len(paginated)} mobile device profiles (total: {len(profiles)})"
        )

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting mobile device profiles")
        return format_error(e)
