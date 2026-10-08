# Copyright 2026, Jamf Software LLC
"""Jamf MCP.

Main entry point for the Model Context Protocol server that enables LLMs to
manage Jamf products and query their API documentation.

This server provides tools for:
- Managing computers and mobile devices
- Working with users and groups (smart and static)
- Accessing policies, configuration profiles, and scripts
- Managing extension attributes, categories, buildings, and departments
- Creating API roles and integrations for programmatic access
- (Optional) Jamf Protect security alerts, computers, and analytics

The server starts with zero credentials required. Setup tools are always
available to help users configure products. Product-specific tools return
helpful error messages when their product is not configured.
"""

import argparse
import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from mcp.server import MCPServer

from . import __version__
from .auth import JamfAuthError
from .client import JamfClient
from .platform_client import PlatformClient
from .prompts import register_prompts
from .protect_client import ProtectClient
from .security_auth import JamfSecurityAuth, JamfSecurityAuthError
from .security_client import JamfSecurityClient
from .tools import register_all_tools, set_client, set_security_client
from .tools._common import set_platform_client, set_protect_client
from .tools._registry import get_registered_tools, get_tool_annotations

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("jamf-mcp")


def get_configuration_status() -> dict:
    """Get configuration status for all products.

    Returns:
        Dict with status for each product:
        - pro_configured: bool
        - protect_configured: bool
        - security_configured: bool
    """
    pro_url = os.environ.get("JAMF_PRO_URL")
    pro_client_id = os.environ.get("JAMF_PRO_CLIENT_ID")
    pro_secret = os.environ.get("JAMF_PRO_CLIENT_SECRET")

    protect_url = os.environ.get("JAMF_PROTECT_URL")
    protect_client_id = os.environ.get("JAMF_PROTECT_CLIENT_ID")
    protect_password = os.environ.get("JAMF_PROTECT_PASSWORD")

    return {
        "pro_configured": bool(pro_url and pro_client_id and pro_secret),
        "protect_configured": bool(protect_url and protect_client_id and protect_password),
        "security_configured": JamfSecurityAuth.is_configured(),
        "platform_configured": PlatformClient.is_configured(),
    }


def _init_pro_client() -> JamfClient | None:
    """Initialize Jamf Pro client if configured."""
    try:
        client = JamfClient.from_env()
        set_client(client)
        logger.info("Jamf Pro client initialized for %s", client.base_url)
        return client
    except JamfAuthError as e:
        logger.warning("Failed to initialize Jamf Pro client: %s", str(e))
    except Exception as e:
        logger.warning("Unexpected error initializing Jamf Pro client: %s", str(e))
    logger.warning("Jamf Pro tools will not be available")
    return None


def _init_protect_client() -> ProtectClient | None:
    """Initialize Jamf Protect client if configured."""
    try:
        client = ProtectClient.from_env()
        if client:
            set_protect_client(client)
            logger.info("Jamf Protect client initialized for %s", client.base_url)
            return client
    except Exception as e:
        logger.warning("Failed to initialize Jamf Protect client: %s", str(e))
        logger.warning("Jamf Protect tools will not be available")
    return None


def _init_security_client() -> JamfSecurityClient | None:
    """Initialize Jamf Security Cloud client if configured."""
    try:
        client = JamfSecurityClient.from_env()
        set_security_client(client)
        logger.info("Jamf Security Cloud client initialized for %s", client.base_url)
        return client
    except JamfSecurityAuthError as e:
        logger.warning("Jamf Security Cloud client not initialized: %s", str(e))
    except Exception as e:
        logger.warning("Unexpected error initializing Jamf Security Cloud client: %s", str(e))
    logger.warning("RISK API tools will not be available")
    return None


def _log_startup_mode(products_configured: int) -> None:
    """Log the server startup mode."""
    if products_configured == 0:
        logger.info("Starting in onboarding mode - no products configured")
        logger.info("Use jamf_get_setup_status() and jamf_configure_help() to get started")
    else:
        logger.info("%d of 4 products configured", products_configured)


@asynccontextmanager
async def jamf_lifespan(server: MCPServer) -> AsyncIterator[None]:
    """Lifespan context manager for Jamf MCP.

    Handles initialization and cleanup of the Jamf Pro and optional Protect clients
    and Jamf Security Cloud client. All products are optional - the server will
    start even with zero credentials configured.
    """
    set_client(None)
    set_protect_client(None)
    set_security_client(None)
    set_platform_client(None)
    config_status = get_configuration_status()
    products_configured = sum(config_status.values())

    # Initialize clients based on configuration
    client = _init_pro_client() if config_status["pro_configured"] else None
    if not config_status["pro_configured"]:
        logger.info("Jamf Pro not configured (set JAMF_PRO_* env vars to enable)")

    protect_client = _init_protect_client() if config_status["protect_configured"] else None
    if not config_status["protect_configured"]:
        logger.info("Jamf Protect not configured (set JAMF_PROTECT_* env vars to enable)")

    security_client = _init_security_client() if config_status["security_configured"] else None
    if not config_status["security_configured"]:
        logger.info("Jamf Security Cloud not configured (set JAMF_SECURITY_* env vars to enable)")

    platform_client = None
    if config_status["platform_configured"]:
        try:
            platform_client = PlatformClient.from_env()
            set_platform_client(platform_client)
            logger.info("Jamf Platform client initialized")
        except ValueError:
            logger.warning(
                "Jamf Platform configuration is invalid; check gateway URL and environment ID"
            )

    _log_startup_mode(products_configured)
    logger.info("Starting Jamf MCP v%s", __version__)

    try:
        yield
    finally:
        set_client(None)
        set_protect_client(None)
        set_security_client(None)
        set_platform_client(None)
        async with AsyncExitStack() as cleanup:
            for configured_client in (client, protect_client, security_client, platform_client):
                if configured_client is not None:
                    cleanup.push_async_callback(configured_client.close)
        logger.info("Server shutdown complete")


INSTRUCTIONS = """Jamf MCP - Manage Jamf products and look up their API documentation.

This server starts with zero credentials required. Use these tools to get started:
- jamf_get_setup_status: Check which products are configured
- jamf_configure_help: Get step-by-step setup instructions

AVAILABLE PRODUCTS:

1. Jamf Pro - Device management for macOS, iOS/iPadOS, tvOS
   - Computers, mobile devices, users
   - Groups (smart and static), policies, profiles
   - Scripts, extension attributes, categories
   - API roles and integrations
   - DDM status reports and conditional-access compliance (not CIS benchmarks)

2. Jamf Protect - Endpoint security
   - Security alerts, enrolled computers, analytics

3. Jamf Security Cloud - Risk management via RISK API
   - Device risk status and overrides

4. Jamf Platform - Read-only Blueprints, compliance and DDM reporting
   - Separate Jamf Account Platform environment integration
   - Benchmark definitions, rule statistics and device results
   - Platform device UUIDs differ from numeric Jamf Pro IDs

5. Jamf API documentation - No tenant credentials required
   - Discover API specs, search endpoints and inspect request/response schemas
   - Lookup tools query the public Jamf documentation MCP service on demand
   - Documentation lookup does not execute the documented tenant operation

IMPORTANT RULES:
- When a product isn't configured, its tools will return setup instructions
- When the user's request is ambiguous about device type (computer, mobile_device,
  or user), ask them to clarify before calling any tool
- This applies to: extension attributes, smart/static groups, prestage enrollments
- For CIS/NIST compliance use Platform benchmark rule/device reports.
  Pro conditional-access compliance is a different report; empty records are no verdict.

Tenant tool results include JSON text and structured data with a 'success' field.
Documentation tools preserve upstream MCP content, structured data and metadata.
Execution failures also set MCP isError.
Use pagination parameters (page, page_size) for large result sets."""


def create_server(
    *,
    tool_filter: str | None = None,
    products: list[str] | None = None,
    remote: bool = False,
    read_only: bool = False,
) -> MCPServer:
    """Build a local or protected remote server with the same tool interface.

    Args:
        tool_filter: Catalogue category to expose.
        products: Jamf products to expose.
        remote: Require the selected protected auth mode and per-tool scopes for HTTP deployment.
        read_only: Exclude every tool without an explicit read-only annotation.
    """
    options = {}
    excluded_tools = frozenset()
    tool_metadata = None
    if remote:
        from mcp.server.auth.routes import build_resource_metadata_url

        from .remote import (
            REMOTE_DISABLED_TOOL_NAMES,
            BearerAuthSettings,
            RemoteToolScopeMiddleware,
            build_remote_auth,
            build_remote_tool_scope_map,
        )

        auth, verifier = build_remote_auth()
        is_bearer = isinstance(auth, BearerAuthSettings)
        scopes = build_remote_tool_scope_map()
        options = {
            "auth": auth,
            "token_verifier": verifier,
            "middleware": [
                RemoteToolScopeMiddleware(
                    scopes,
                    resource_metadata_url=(
                        None
                        if is_bearer
                        else str(build_resource_metadata_url(auth.resource_server_url))
                    ),
                    advertise_security_schemes=not is_bearer,
                )
            ],
        }
        excluded_tools = REMOTE_DISABLED_TOOL_NAMES
        if not is_bearer:
            tool_metadata = {
                name: {"securitySchemes": [{"type": "oauth2", "scopes": sorted(required)}]}
                for name, required in scopes.items()
            }
    if read_only:
        excluded_tools = excluded_tools.union(
            func.__name__
            for func, _ in get_registered_tools()
            if (annotation := get_tool_annotations(func)) is None
            or annotation.read_only_hint is not True
        )
    server = MCPServer(
        "jamf-mcp",
        version=__version__,
        instructions=INSTRUCTIONS,
        lifespan=jamf_lifespan,
        **options,
    )
    register_all_tools(
        server,
        tool_filter=tool_filter,
        allowed_products=products,
        excluded_tools=excluded_tools,
        tool_metadata=tool_metadata,
    )
    register_prompts(server)
    return server


mcp = create_server()


def main() -> None:
    """Entry point for Jamf MCP."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Jamf MCP: Jamf management and API documentation")
    parser.add_argument(
        "--tool-filter",
        choices=["api", "complex", "all"],
        help="Filter tools by type (overrides JAMF_TOOL_FILTER env var)",
    )
    parser.add_argument(
        "--products",
        nargs="+",
        help="Filter tools by product (e.g. pro platform docs). Overrides JAMF_PRODUCTS env var.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default=os.environ.get("JAMF_MCP_TRANSPORT", "stdio"),
        help="Local stdio (default) or protected Streamable HTTP",
    )
    parser.add_argument("--host", default=os.environ.get("JAMF_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=os.environ.get("JAMF_MCP_PORT", "8000"))
    parser.add_argument("--read-only", action="store_true", help="Expose only read-only tools")
    parser.add_argument("--ssl-certfile", help="TLS certificate for Streamable HTTP")
    parser.add_argument("--ssl-keyfile", help="TLS private key for Streamable HTTP")
    args = parser.parse_args()
    if bool(args.ssl_certfile) != bool(args.ssl_keyfile):
        parser.error("TLS requires both --ssl-certfile and --ssl-keyfile")
    if args.transport == "stdio" and args.ssl_certfile:
        parser.error("TLS options require --transport streamable-http")
    if args.transport not in {"stdio", "streamable-http"}:
        parser.error("JAMF_MCP_TRANSPORT must be stdio or streamable-http")

    # Determine filter: CLI arg > Env var > Default (None = all)
    tool_filter = args.tool_filter or os.environ.get("JAMF_TOOL_FILTER")

    # Determine products: CLI arg > Env var > Default (None = all)
    products = args.products
    if not products and os.environ.get("JAMF_PRODUCTS"):
        products = os.environ.get("JAMF_PRODUCTS").split(",")
        # clean whitespace
        products = [p.strip() for p in products if p.strip()]

    logger.info("Initializing Jamf MCP v%s", __version__)

    if tool_filter:
        logger.info("Applying tool filter: %s", tool_filter)

    if products:
        logger.info("Applying product filter: %s", products)

    try:
        server = create_server(
            tool_filter=tool_filter,
            products=products,
            remote=args.transport == "streamable-http",
            read_only=args.read_only,
        )
    except ValueError as error:
        parser.error(str(error))
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        from urllib.parse import urlsplit

        from mcp.server.transport_security import TransportSecuritySettings

        from .remote import build_remote_http_app, get_remote_resource_url

        public = urlsplit(get_remote_resource_url(server))
        security = TransportSecuritySettings(
            allowed_hosts=[public.netloc, "127.0.0.1:*", "localhost:*", "[::1]:*"],
            allowed_origins=[f"https://{public.netloc}"],
        )
        import uvicorn

        app = build_remote_http_app(
            server,
            host=args.host,
            stateless_http=True,
            json_response=True,
            transport_security=security,
        )
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            ssl_certfile=args.ssl_certfile,
            ssl_keyfile=args.ssl_keyfile,
        )


if __name__ == "__main__":
    main()
