# Copyright 2026, Jamf Software LLC
"""API Role and Integration management tools for Jamf Pro.

This module provides tools for creating API roles and API integrations (clients)
for programmatic access to Jamf Pro. Useful for setting up service accounts
with specific permissions.
"""

import logging
from typing import Optional

from ..client import JamfAPIError
from ._common import format_error, format_response, get_client_safe
from ._registry import jamf_tool

logger = logging.getLogger(__name__)


@jamf_tool(read_only=True)
async def jamf_get_api_role_privileges(
    search: Optional[str] = None,
) -> str:
    """Get available API role privileges from Jamf Pro.

    Retrieves the list of privileges that can be assigned to API roles.
    Use this to discover available permissions when creating API roles.

    Args:
        search: Filter privileges by keyword (case-insensitive partial match)

    Returns:
        JSON containing list of available privilege strings that can be
        assigned to API roles.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        result = await client.v1_get("api-role-privileges")
        privileges = result.get("privileges", [])

        if search:
            search_lower = search.lower()
            privileges = [p for p in privileges if search_lower in p.lower()]

        return format_response(
            {"privileges": privileges, "totalCount": len(privileges)},
            f"Retrieved {len(privileges)} privileges"
        )

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting API role privileges")
        return format_error(e)


@jamf_tool(read_only=True)
async def jamf_get_api_roles(
    role_id: Optional[int] = None,
    name: Optional[str] = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get API roles from Jamf Pro.

    Retrieves API roles which define sets of privileges for API integrations.
    API roles control what actions an API client can perform.

    Args:
        role_id: Specific role ID to retrieve full details
        name: Filter roles by display name (partial match)
        page: Page number for pagination (0-indexed, default: 0)
        page_size: Number of results per page (default: 100)

    Returns:
        JSON containing API role list or detailed role with assigned privileges.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if role_id:
            result = await client.v1_get(f"api-roles/{role_id}")
            return format_response(result, f"Retrieved API role ID {role_id}")

        params = {"page": page, "page-size": page_size}
        if name:
            params["filter"] = f'displayName=="{name}*"'

        result = await client.v1_get("api-roles", params=params)
        count = result.get("totalCount", len(result.get("results", [])))
        return format_response(result, f"Retrieved {count} API roles")

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting API roles")
        return format_error(e)


@jamf_tool(destructive=False)
async def jamf_create_api_role(
    display_name: str,
    privileges: list[str],
) -> str:
    """Create an API role in Jamf Pro.

    Creates a new API role with specified privileges. API roles define
    permissions that can be assigned to API integrations (clients).

    Args:
        display_name: Name for the API role (required)
        privileges: List of privilege strings to grant (required)
            Use jamf_get_api_role_privileges() to see available privileges.

            Common privileges for computer management:
            - "Read Computers"
            - "Update Computers"
            - "Create Computers"
            - "Delete Computers"

    Returns:
        JSON with creation result including new role ID.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if not display_name:
            return format_error(ValueError("display_name is required"))

        if not privileges:
            return format_error(ValueError("privileges list is required and cannot be empty"))

        payload = {
            "displayName": display_name,
            "privileges": privileges,
        }

        result = await client.v1_post("api-roles", payload)
        return format_response(result, f"Created API role '{display_name}'")

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error creating API role")
        return format_error(e)


@jamf_tool(read_only=True)
async def jamf_get_api_integrations(
    integration_id: Optional[int] = None,
    name: Optional[str] = None,
    page: int = 0,
    page_size: int = 100,
) -> str:
    """Get API integrations from Jamf Pro.

    Retrieves API integrations (clients) used for programmatic API access.
    Integrations are assigned API roles and generate client credentials.

    Args:
        integration_id: Specific integration ID to retrieve full details
        name: Filter integrations by display name (partial match)
        page: Page number for pagination (0-indexed, default: 0)
        page_size: Number of results per page (default: 100)

    Returns:
        JSON containing API integration list or detailed integration
        with assigned roles and configuration.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if integration_id:
            result = await client.v1_get(f"api-integrations/{integration_id}")
            return format_response(result, f"Retrieved API integration ID {integration_id}")

        params = {"page": page, "page-size": page_size}
        if name:
            params["filter"] = f'displayName=="{name}*"'

        result = await client.v1_get("api-integrations", params=params)
        count = result.get("totalCount", len(result.get("results", [])))
        return format_response(result, f"Retrieved {count} API integrations")

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error getting API integrations")
        return format_error(e)


@jamf_tool(destructive=False)
async def jamf_create_api_integration(
    display_name: str,
    api_role_names: list[str],
    enabled: bool = True,
    access_token_lifetime_seconds: int = 1800,
) -> str:
    """Create an API integration (client) in Jamf Pro.

    Creates a new API integration with assigned API roles. After creation,
    call jamf_create_api_client_credentials() to generate authentication credentials.

    Args:
        display_name: Name for the API integration (required)
        api_role_names: List of API role display names to assign (required)
            These must exactly match existing API role names.
        enabled: Whether the integration is enabled (default: True)
        access_token_lifetime_seconds: Token lifetime in seconds (default: 1800 = 30 min)

    Returns:
        JSON with creation result including new integration ID.
        Note: Call jamf_create_api_client_credentials() next to get
        the client_id and client_secret for authentication.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if not display_name:
            return format_error(ValueError("display_name is required"))

        if not api_role_names:
            return format_error(ValueError("api_role_names list is required and cannot be empty"))

        payload = {
            "displayName": display_name,
            "authorizationScopes": api_role_names,
            "enabled": enabled,
            "accessTokenLifetimeSeconds": access_token_lifetime_seconds,
        }

        result = await client.v1_post("api-integrations", payload)
        return format_response(
            result,
            f"Created API integration '{display_name}'. Use jamf_create_api_client_credentials() "
            f"with the integration ID to generate client credentials."
        )

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error creating API integration")
        return format_error(e)


@jamf_tool
async def jamf_create_api_client_credentials(
    integration_id: int,
) -> str:
    """Generate client credentials for an API integration.

    Creates new OAuth2 client credentials (client_id and client_secret)
    for the specified API integration.

    IMPORTANT: The client_secret is only shown ONCE and cannot be retrieved
    again. Store it securely immediately after creation.

    Args:
        integration_id: ID of the API integration to generate credentials for

    Returns:
        JSON containing client_id and client_secret.
        SAVE THE CLIENT_SECRET IMMEDIATELY - it cannot be retrieved again!
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        if not integration_id:
            return format_error(ValueError("integration_id is required"))

        result = await client.v1_post(
            f"api-integrations/{integration_id}/client-credentials",
            {}
        )
        return format_response(
            result,
            f"Generated client credentials for integration ID {integration_id}. "
            "IMPORTANT: Save the client_secret now - it cannot be retrieved again!"
        )

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error creating API client credentials")
        return format_error(e)


@jamf_tool(destructive=False)
async def jamf_create_computer_update_api_client(
    role_name: str = "Computer Update Role",
    integration_name: str = "Computer Update Client",
    additional_privileges: Optional[list[str]] = None,
) -> str:
    """Create an API role and client configured for updating computers.

    Convenience function that creates both an API role with computer update
    privileges and an API integration in one step. Call
    jamf_create_api_client_credentials() after to get authentication credentials.

    Args:
        role_name: Name for the API role (default: "Computer Update Role")
        integration_name: Name for the integration (default: "Computer Update Client")
        additional_privileges: Extra privileges beyond defaults (optional)
            Default privileges: ["Read Computers", "Update Computers"]

    Returns:
        JSON with creation results including role ID and integration ID.
        Call jamf_create_api_client_credentials() with the integration ID
        to complete setup.
    """
    client, error = get_client_safe()
    if error:
        return error

    try:
        privileges = ["Read Computers", "Update Computers"]
        if additional_privileges:
            privileges.extend(additional_privileges)
            privileges = list(dict.fromkeys(privileges))

        role_payload = {
            "displayName": role_name,
            "privileges": privileges,
        }
        role_result = await client.v1_post("api-roles", role_payload)
        role_id = role_result.get("id")

        integration_payload = {
            "displayName": integration_name,
            "authorizationScopes": [role_name],
            "enabled": True,
            "accessTokenLifetimeSeconds": 1800,
        }
        integration_result = await client.v1_post("api-integrations", integration_payload)
        integration_id = integration_result.get("id")

        return format_response(
            {
                "role": {
                    "id": role_id,
                    "displayName": role_name,
                    "privileges": privileges,
                },
                "integration": {
                    "id": integration_id,
                    "displayName": integration_name,
                },
                "next_step": f"Call jamf_create_api_client_credentials(integration_id={integration_id}) "
                             "to generate the client_id and client_secret for authentication."
            },
            f"Created API role '{role_name}' and integration '{integration_name}'"
        )

    except JamfAPIError as e:
        return format_error(e)
    except Exception as e:
        logger.exception("Error creating computer update API client")
        return format_error(e)
