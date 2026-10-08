# Copyright 2026, Jamf Software LLC
"""App Installer management tools for Jamf Pro.

This module provides tools for managing Jamf App Catalog titles and
App Installer deployments.
"""

import logging
from typing import Optional

from ..client import JamfAPIError
from ._common import format_error, format_response, get_client_safe
from ._registry import jamf_tool

logger = logging.getLogger(__name__)


def _is_safe_deployment_id(value: object) -> bool:
    """Accept an opaque ASCII path segment without URL syntax or dot segments."""
    return (
        isinstance(value, str)
        and bool(value)
        and value not in {".", ".."}
        and all(
            character.isascii() and (character.isalnum() or character in "-._~")
            for character in value
        )
    )


@jamf_tool(read_only=True)
async def jamf_get_app_installer_titles(
    title_name: Optional[str] = None,
    publisher: Optional[str] = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get available App Installer titles from Jamf App Catalog.

    Retrieves the list of available software titles in the Jamf App Catalog
    that can be deployed as App Installers. These are pre-packaged applications
    maintained by Jamf for easy deployment.

    IMPORTANT: Use short, simple search terms (e.g., "Firefox" not "Mozilla Firefox",
    "Chrome" not "Google Chrome"). The search performs a contains match so partial
    names work well. If the search returns multiple results, present the list to the
    user and ask them to pick the correct one before proceeding with deployment.

    Args:
        title_name: Filter by app title name (contains match, e.g., "Firefox", "Chrome", "Slack").
            Use short keywords for best results - the search matches anywhere in the title name.
        publisher: Filter by publisher name (contains match, e.g., "Microsoft", "Adobe")
        page: Page number for pagination (0-indexed, default: 0)
        page_size: Number of results per page (default: 100, max: 999)

    Returns:
        JSON containing available App Installer titles with id, titleName,
        bundleId, publisher, version, and iconUrl for each title.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        params = {"page": page, "page-size": min(page_size, 999)}

        filters = []
        if title_name:
            filters.append(f'titleName=="*{title_name}*"')
        if publisher:
            filters.append(f'publisher=="*{publisher}*"')
        if filters:
            params["filter"] = ";".join(filters)

        result = await client.v1_get("app-installers/titles", params=params)
        count = result.get("totalCount", len(result.get("results", [])))
        return format_response(result, f"Retrieved {count} App Installer titles from catalog")

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting App Installer titles")
        return format_error(e)


@jamf_tool(read_only=True)
async def jamf_get_app_installer_deployments(
    deployment_id: Optional[str] = None,
    name: Optional[str] = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get App Installer deployments from Jamf Pro.

    Retrieves App Installer deployments which define how Jamf App Catalog
    titles are deployed to devices via smart groups.

    Args:
        deployment_id: Opaque ASCII deployment ID for full configuration details.
            Accepts letters, digits, hyphen, underscore, dot and tilde; not dot segments.
        name: Filter deployments by name (partial match)
        page: Page number for pagination (0-indexed, default: 0)
        page_size: Number of results per page (default: 100)

    Returns:
        JSON containing deployment list or detailed deployment configuration
        including target smart group and deployment settings.
    """
    if deployment_id and not _is_safe_deployment_id(deployment_id):
        return format_error(ValueError("deployment_id must be a single safe ASCII identifier"))

    client, error = get_client_safe()
    if error:
        return error

    try:
        if deployment_id:
            result = await client.v1_get(f"app-installers/deployments/{deployment_id}")
            return format_response(result, f"Retrieved App Installer deployment ID {deployment_id}")

        result = await client.v1_get("app-installers/deployments")
        deployments = result.get("results", result) if isinstance(result, dict) else result

        if name and isinstance(deployments, list):
            deployments = [d for d in deployments if name.lower() in d.get("name", "").lower()]

        if isinstance(deployments, list):
            start = page * page_size
            end = start + page_size
            paginated = deployments[start:end]
            return format_response(
                {"results": paginated, "totalCount": len(deployments)},
                f"Retrieved {len(paginated)} App Installer deployments (total: {len(deployments)})"
            )

        return format_response(result, "Retrieved App Installer deployments")

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting App Installer deployments")
        return format_error(e)


@jamf_tool
async def jamf_create_app_installer_deployment(
    name: str,
    app_title_id: str,
    smart_group_id: int,
    enabled: bool = True,
    site_id: int = -1,
    category_id: int = -1,
    deployment_type: str = "INSTALL_AUTOMATICALLY",
    update_behavior: str = "AUTOMATIC",
    notification_interval: int = 24,
    install_predefined_config_profiles: bool = True,
) -> str:
    """Create an App Installer deployment in Jamf Pro.

    Creates a new App Installer deployment to deploy a Jamf App Catalog
    software title to devices in a smart group.

    IMPORTANT: Before creating a deployment, always use jamf_get_app_installer_titles()
    to search for the app first. If the search returns multiple matches, present the
    list to the user and ask them to confirm which app title to deploy.

    Args:
        name: Deployment name (required)
        app_title_id: App title ID from jamf_get_app_installer_titles (required)
        smart_group_id: Target smart group ID (required)
        enabled: Whether deployment is active (default: True)
        site_id: Site ID to assign to (-1 for none)
        category_id: Category ID for Self Service (-1 for none)
        deployment_type: How to deploy (default: "INSTALL_AUTOMATICALLY"):
            - "INSTALL_AUTOMATICALLY" - Install without user action
            - "SELF_SERVICE" - Available in Self Service for users to install
        update_behavior: How updates are handled (default: "AUTOMATIC"):
            - "AUTOMATIC" - Auto-update when new versions available
            - "MANUAL" - Require manual update
        notification_interval: Hours between update notifications (default: 24)
        install_predefined_config_profiles: Install related profiles (default: True)

    Returns:
        JSON with creation result including new deployment ID.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        deployment_data = {
            "name": name,
            "enabled": enabled,
            "appTitleId": str(app_title_id),
            "siteId": site_id,
            "categoryId": category_id,
            "smartGroupId": str(smart_group_id),
            "deploymentType": deployment_type,
            "updateBehavior": update_behavior,
            "notificationSettings": {
                "notificationMessage": None,
                "notificationInterval": notification_interval,
                "deadlineMessage": None,
                "deadline": None,
            },
            "installPredefinedConfigProfiles": install_predefined_config_profiles,
        }

        result = await client.v1_post("app-installers/deployments", deployment_data)
        return format_response(result, f"Created App Installer deployment '{name}'")

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error creating App Installer deployment")
        return format_error(e)


@jamf_tool(read_only=True)
async def jamf_get_app_installers(
    app_id: Optional[str] = None,
    name: Optional[str] = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get App Installers from Jamf Pro (convenience alias).

    This is a convenience function that returns app titles from the catalog.
    For more specific queries, use:
    - jamf_get_app_installer_titles() for available titles
    - jamf_get_app_installer_deployments() for existing deployments

    IMPORTANT: Use short, simple search terms (e.g., "Firefox" not "Mozilla Firefox").
    The search does a contains match. If multiple results are returned, present them
    to the user and ask which one they want before proceeding.

    Args:
        app_id: Specific deployment ID to retrieve; uses the same safe identifier rules
            as jamf_get_app_installer_deployments.
        name: Filter by app name (contains match, use short keywords like "Firefox", "Slack")
        page: Page number for pagination (0-indexed, default: 0)
        page_size: Number of results per page (default: 100)

    Returns:
        JSON containing App Installer information.
    """
    if app_id:
        return await jamf_get_app_installer_deployments(deployment_id=app_id)
    return await jamf_get_app_installer_titles(title_name=name, page=page, page_size=page_size)
