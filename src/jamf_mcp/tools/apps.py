# Copyright 2026, Jamf Software LLC
"""App and content management tools for Jamf Pro.

This module provides tools for retrieving Mac apps, mobile device apps,
restricted software, eBooks, and patch policies.
"""

import logging
from typing import Optional

from ..client import JamfAPIError
from ._common import format_error, format_response, get_client_safe
from ._registry import jamf_tool

logger = logging.getLogger(__name__)


# =============================================================================
# Mac Apps
# =============================================================================


@jamf_tool(read_only=True)
async def jamf_get_mac_apps(
    app_id: Optional[int] = None,
    name: Optional[str] = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get Mac App Store apps from Jamf Pro.

    Retrieves Mac App Store applications that can be deployed to macOS computers.
    These are VPP (Volume Purchase Program) apps managed through Apple Business Manager.

    Args:
        app_id: Specific Mac App ID for full configuration including scope
        name: Filter apps by name (partial match)
        page: Page number for pagination (0-indexed, default: 0)
        page_size: Number of results per page (default: 100)

    Returns:
        JSON containing Mac App list or detailed app configuration including
        scope, VPP assignment, and deployment settings.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if app_id:
            result = await client.classic_get("macapplications", app_id)
            return format_response(
                result.get("mac_application", result),
                f"Retrieved Mac App ID {app_id}"
            )

        result = await client.classic_get("macapplications")
        apps = result.get("mac_applications", [])

        if name:
            apps = [a for a in apps if name.lower() in a.get("name", "").lower()]

        start = page * page_size
        end = start + page_size
        paginated = apps[start:end]

        return format_response(
            {"mac_applications": paginated, "totalCount": len(apps)},
            f"Retrieved {len(paginated)} Mac apps (total: {len(apps)})"
        )

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting Mac apps")
        return format_error(e)


# =============================================================================
# Mobile Device Apps
# =============================================================================


@jamf_tool(read_only=True)
async def jamf_get_mobile_device_apps(
    app_id: Optional[int] = None,
    name: Optional[str] = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get mobile device apps from Jamf Pro.

    Retrieves iOS/iPadOS apps that can be deployed to mobile devices.
    Includes VPP (Volume Purchase Program) apps and in-house enterprise apps.

    Args:
        app_id: Specific Mobile Device App ID for full configuration including scope
        name: Filter apps by name (partial match)
        page: Page number for pagination (0-indexed, default: 0)
        page_size: Number of results per page (default: 100)

    Returns:
        JSON containing Mobile Device App list or detailed app configuration
        including scope, VPP assignment, and app configuration settings.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if app_id:
            result = await client.classic_get("mobiledeviceapplications", app_id)
            return format_response(
                result.get("mobile_device_application", result),
                f"Retrieved Mobile Device App ID {app_id}"
            )

        result = await client.classic_get("mobiledeviceapplications")
        apps = result.get("mobile_device_applications", [])

        if name:
            apps = [a for a in apps if name.lower() in a.get("name", "").lower()]

        start = page * page_size
        end = start + page_size
        paginated = apps[start:end]

        return format_response(
            {"mobile_device_applications": paginated, "totalCount": len(apps)},
            f"Retrieved {len(paginated)} Mobile Device apps (total: {len(apps)})"
        )

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting Mobile Device apps")
        return format_error(e)


# =============================================================================
# Restricted Software
# =============================================================================


@jamf_tool(read_only=True)
async def jamf_get_restricted_software(
    restricted_software_id: Optional[int] = None,
    name: Optional[str] = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get restricted software from Jamf Pro.

    Retrieves restricted software configurations which define applications
    that should be blocked, removed, or monitored on managed computers.

    Args:
        restricted_software_id: Specific Restricted Software ID for full scope details
        name: Filter by name (partial match)
        page: Page number for pagination (0-indexed, default: 0)
        page_size: Number of results per page (default: 100)

    Returns:
        JSON containing Restricted Software list or detailed configuration
        including process name, scope, and restriction settings.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if restricted_software_id:
            result = await client.classic_get("restrictedsoftware", restricted_software_id)
            return format_response(
                result.get("restricted_software", result),
                f"Retrieved Restricted Software ID {restricted_software_id}"
            )

        result = await client.classic_get("restrictedsoftware")
        items = result.get("restricted_software", [])

        if name:
            items = [i for i in items if name.lower() in i.get("name", "").lower()]

        start = page * page_size
        end = start + page_size
        paginated = items[start:end]

        return format_response(
            {"restricted_software": paginated, "totalCount": len(items)},
            f"Retrieved {len(paginated)} restricted software entries (total: {len(items)})"
        )

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting restricted software")
        return format_error(e)


# =============================================================================
# eBooks
# =============================================================================


@jamf_tool(read_only=True)
async def jamf_get_ebooks(
    ebook_id: Optional[int] = None,
    name: Optional[str] = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get eBooks from Jamf Pro.

    Retrieves eBooks that can be deployed to mobile devices. Typically managed
    through VPP (Volume Purchase Program) via Apple Business Manager.

    Args:
        ebook_id: Specific eBook ID for full configuration including scope
        name: Filter eBooks by name (partial match)
        page: Page number for pagination (0-indexed, default: 0)
        page_size: Number of results per page (default: 100)

    Returns:
        JSON containing eBook list or detailed eBook configuration
        including scope and VPP assignment settings.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if ebook_id:
            result = await client.classic_get("ebooks", ebook_id)
            return format_response(
                result.get("ebook", result),
                f"Retrieved eBook ID {ebook_id}"
            )

        result = await client.classic_get("ebooks")
        ebooks = result.get("ebooks", [])

        if name:
            ebooks = [e for e in ebooks if name.lower() in e.get("name", "").lower()]

        start = page * page_size
        end = start + page_size
        paginated = ebooks[start:end]

        return format_response(
            {"ebooks": paginated, "totalCount": len(ebooks)},
            f"Retrieved {len(paginated)} eBooks (total: {len(ebooks)})"
        )

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting eBooks")
        return format_error(e)


# =============================================================================
# Patch Policies
# =============================================================================


@jamf_tool(read_only=True)
async def jamf_get_patch_policies(
    patch_policy_id: Optional[int] = None,
    name: Optional[str] = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get patch policies from Jamf Pro.

    Retrieves patch management policies that define software update deployment
    for third-party applications on managed computers.

    Args:
        patch_policy_id: Specific Patch Policy ID for full scope details
        name: Filter by name (partial match)
        page: Page number for pagination (0-indexed, default: 0)
        page_size: Number of results per page (default: 100)

    Returns:
        JSON containing Patch Policy list or detailed policy configuration
        including target version, scope, and deployment settings.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if patch_policy_id:
            result = await client.classic_get("patchpolicies", patch_policy_id)
            return format_response(
                result.get("patch_policy", result),
                f"Retrieved Patch Policy ID {patch_policy_id}"
            )

        result = await client.classic_get("patchpolicies")
        policies = result.get("patch_policies", [])

        if name:
            policies = [p for p in policies if name.lower() in p.get("name", "").lower()]

        start = page * page_size
        end = start + page_size
        paginated = policies[start:end]

        return format_response(
            {"patch_policies": paginated, "totalCount": len(policies)},
            f"Retrieved {len(paginated)} patch policies (total: {len(policies)})"
        )

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting patch policies")
        return format_error(e)
