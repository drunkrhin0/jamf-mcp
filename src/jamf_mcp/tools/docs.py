# Copyright 2026, Jamf Software LLC
"""Documentation lookup tools for Jamf MCP.

Calls the public Jamf documentation MCP service on demand. No tenant credentials
are used or forwarded. Only approved documentation operations can be proxied.
"""

import json
import logging
from typing import Any

from mcp import Client
from mcp_types import CallToolResult, TextContent

from ._registry import jamf_tool

logger = logging.getLogger(__name__)
JAMF_DOCS_MCP_URL = "https://developer.jamf.com/mcp"

DOCUMENTATION_TOOLS = frozenset(
    {"list-specs", "list-endpoints", "get-endpoint", "search-endpoints", "get-server-variables"}
)

_upstream_tools_cache: list[dict] | None = None


async def get_upstream_tools() -> list[dict]:
    """
    Connect to the Jamf docs MCP server and list available tools.
    Results are cached to avoid repeated connections.
    """
    global _upstream_tools_cache

    if _upstream_tools_cache is not None:
        return _upstream_tools_cache

    try:
        async with Client(JAMF_DOCS_MCP_URL) as client:
            tools = []
            cursor = None
            while True:
                tools_result = await client.list_tools(cursor=cursor)
                tools.extend(
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.input_schema,
                    }
                    for tool in tools_result.tools
                    if tool.name in DOCUMENTATION_TOOLS
                )
                cursor = tools_result.next_cursor
                if cursor is None:
                    break
            _upstream_tools_cache = tools
            logger.info("Cached %d documentation tools", len(tools))
            return tools
    except Exception as e:
        logger.error(f"Failed to connect to Jamf docs MCP server: {e}")
        raise


async def call_upstream_tool(tool_name: str, arguments: dict[str, Any]) -> CallToolResult:
    """Call an approved documentation tool, preserving its full MCP result."""
    if tool_name not in DOCUMENTATION_TOOLS:
        raise ValueError(f"Unsupported documentation tool: {tool_name}")
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a JSON object")
    async with Client(JAMF_DOCS_MCP_URL) as client:
        return await client.call_tool(tool_name, arguments)


def json_result(data: Any, *, is_error: bool = False) -> CallToolResult:
    """Return local documentation metadata or an execution error."""
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, indent=2))],
        structured_content=data,
        is_error=is_error,
    )


def resolve_spec_title(title: str) -> str:
    """Retain the original Pro shorthand while using upstream's qualified titles."""
    return {
        "Jamf Pro API": "jamf-pro=Jamf Pro API",
        "Classic API": "jamf-pro=Classic API",
    }.get(title, title)


async def forward_documentation_tool(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    error_context: dict[str, Any] | None = None,
) -> CallToolResult:
    """Forward documentation calls and format local failures in one place.

    Args:
        tool_name: Approved upstream documentation operation.
        arguments: Arguments mapped by the local tool.
        error_context: Local input fields retained in connection/validation errors.

    Returns:
        The unchanged upstream result, or a structured execution error.
    """
    try:
        if "title" in arguments:
            arguments = {**arguments, "title": resolve_spec_title(arguments["title"])}
        return await call_upstream_tool(tool_name, arguments)
    except Exception as error:
        return json_result({"error": str(error), **(error_context or {})}, is_error=True)


@jamf_tool(read_only=True)
async def list_jamf_api_tools() -> CallToolResult:
    """List all available tools from the Jamf Developer Documentation MCP server.

    This returns a list of tools that can be used to search and retrieve
    Jamf Pro API documentation. Use this to discover what documentation
    tools are available from the upstream server.

    Returns:
        A JSON string containing the list of available tools with their
        names, descriptions, and input schemas.
    """
    try:
        tools = await get_upstream_tools()
        return json_result(tools)
    except Exception as e:
        return json_result({"error": str(e)}, is_error=True)


@jamf_tool(read_only=True)
async def list_available_specs() -> CallToolResult:
    """List all available Jamf API specifications.

    Returns the list of OpenAPI specs available for querying. Use the 'title'
    from this list when calling other tools that require a spec title.

    Common specs:
    - "jamf-pro=Jamf Pro API" - Modern Pro REST API
    - "jamf-pro=Classic API" - Classic Pro API
    - "platform-api=Blueprints API" - Platform Blueprints

    Returns:
        JSON array of available API specs with titles and descriptions.
    """
    return await forward_documentation_tool("list-specs", {})


@jamf_tool(read_only=True)
async def search_jamf_api(pattern: str) -> CallToolResult:
    """Search Jamf API documentation for endpoints matching a pattern.

    Use this to find API endpoints related to specific functionality like
    "computers", "mobile", "scripts", "policies", "prestage", etc.

    This searches across ALL available API specs (Jamf Pro API, Classic API, etc.)
    and returns matching paths, operations, and schemas.

    Args:
        pattern: Case-insensitive search pattern.
                 Examples: "computers", "mobile", "prestage", "policies",
                 "scripts", "extension", "configuration", "profile"

    Returns:
        Search results containing matching endpoint paths, operations,
        and schema definitions from all available API specs.
    """
    return await forward_documentation_tool(
        "search-endpoints", {"pattern": pattern}, error_context={"pattern": pattern}
    )


@jamf_tool(read_only=True)
async def list_api_endpoints(spec_title: str = "Jamf Pro API") -> CallToolResult:
    """List all API endpoints for a specific Jamf API spec.

    Returns all available paths and their HTTP methods for the specified API.

    Args:
        spec_title: Title returned by list_available_specs(), such as
                    "jamf-pro=Jamf Pro API" or "platform-api=Blueprints API".
                    The Pro shorthand "Jamf Pro API" (default) and "Classic API"
                    also works. Use the returned paths in endpoint lookups.

    Returns:
        List of all endpoint paths with their HTTP methods and summaries.
    """
    return await forward_documentation_tool(
        "list-endpoints", {"title": spec_title}, error_context={"spec_title": spec_title}
    )


@jamf_tool(read_only=True)
async def get_endpoint_details(
    path: str, method: str, spec_title: str = "Jamf Pro API"
) -> CallToolResult:
    """Get detailed documentation for a specific Jamf API endpoint.

    Use this to get full details about an endpoint including:
    - Operation summary and description
    - Required and optional parameters
    - Security requirements
    - Tags and operation ID

    Args:
        path: Exact OpenAPI path returned by list_api_endpoints or search_jamf_api.
              Paths are relative to the specification's server URL and can omit
              /api or /JSSResource, for example "/v1/computers-inventory" or
              "/policies". Preserve the returned path instead of adding a prefix.
        method: HTTP method (GET, POST, PUT, DELETE, PATCH)
        spec_title: Specification title returned by list_available_specs().
                    The Pro shorthand "Jamf Pro API" and "Classic API" also works.

    Returns:
        Detailed documentation for the specified endpoint.
    """
    return await forward_documentation_tool(
        "get-endpoint",
        {"path": path, "method": method.upper(), "title": spec_title},
        error_context={"path": path, "method": method},
    )


@jamf_tool(read_only=True)
async def get_request_body_schema(
    path: str, method: str, spec_title: str = "Jamf Pro API"
) -> CallToolResult:
    """Get the request body schema for a specific endpoint.

    Use this for POST, PUT, and PATCH endpoints to understand
    what data to send in the request body.

    Args:
        path: The API endpoint path.
        method: HTTP method (typically POST, PUT, or PATCH)
        spec_title: Title of the OpenAPI spec.

    Returns:
        JSON schema definition for the request body.
    """
    return await endpoint_schema(path, method, spec_title, request_body=True)


@jamf_tool(read_only=True)
async def get_response_schema(
    path: str, method: str, spec_title: str = "Jamf Pro API", status_code: str = "200"
) -> CallToolResult:
    """Get the response schema for a specific endpoint.

    Use this to understand what data structure to expect from an API response.

    Args:
        path: The API endpoint path.
        method: HTTP method (GET, POST, PUT, DELETE, PATCH)
        spec_title: Title of the OpenAPI spec.
        status_code: HTTP status code to get schema for (default: "200")

    Returns:
        JSON schema definition for the response body.
    """
    return await endpoint_schema(path, method, spec_title, status_code=status_code)


async def endpoint_schema(
    path: str,
    method: str,
    spec_title: str,
    *,
    request_body: bool = False,
    status_code: str = "200",
) -> CallToolResult:
    """Extract schema documentation while retaining references and upstream metadata."""
    context = {"path": path, "method": method}
    result = await forward_documentation_tool(
        "get-endpoint",
        {"path": path, "method": method.upper(), "title": spec_title},
        error_context=context,
    )
    if result.is_error:
        return result
    try:
        document = result.structured_content
        if not isinstance(document, dict) or "paths" not in document:
            document = next(
                json.loads(block.text) for block in result.content if isinstance(block, TextContent)
            )
        operation = document["paths"][path][method.lower()]
        if request_body:
            if "requestBody" not in operation:
                raise ValueError("Endpoint does not document a request body")
            data = {"requestBody": operation["requestBody"]}
        else:
            responses = operation.get("responses", {})
            if status_code not in responses:
                raise ValueError(f"Endpoint does not document response status {status_code}")
            data = {"status_code": status_code, "response": responses[status_code]}
        data["components"] = document.get("components", {})
        return result.model_copy(
            update={
                "content": [TextContent(type="text", text=json.dumps(data, indent=2))]
                + [block for block in result.content if not isinstance(block, TextContent)],
                "structured_content": data,
            }
        )
    except Exception as error:
        return json_result({"error": str(error), **context}, is_error=True)


@jamf_tool(read_only=True)
async def call_jamf_docs_tool(tool_name: str, arguments: str = "{}") -> CallToolResult:
    """Call an approved read-only documentation tool on the Jamf docs MCP server.

    Use list_jamf_api_tools() first to see available tools and their schemas,
    then use this to call a specific tool with custom arguments.

    Available upstream tools:
    - list-specs: List all API specs
    - list-endpoints: List endpoints for a spec (requires: title)
    - get-endpoint: Get endpoint details (requires: path, method, title)
    - search-endpoints: Search across specs (requires: pattern)
    - get-server-variables: Get server config (requires: title)

    Args:
        tool_name: The name of the tool to call on the Jamf docs server.
        arguments: JSON string of arguments to pass to the tool.

    Returns:
        The result from the upstream tool call.
    """
    try:
        args = json.loads(arguments)
    except json.JSONDecodeError as e:
        return json_result({"error": f"Invalid JSON arguments: {e}"}, is_error=True)
    except Exception as e:
        return json_result({"error": str(e), "tool_name": tool_name}, is_error=True)
    return await forward_documentation_tool(tool_name, args, error_context={"tool_name": tool_name})


@jamf_tool(read_only=True)
async def refresh_jamf_docs_cache() -> CallToolResult:
    """Refresh the cached list of tools from the Jamf docs MCP server.

    Call this if tools seem outdated or if you're getting unexpected errors.

    Returns:
        Status message indicating success or failure of cache refresh.
    """
    global _upstream_tools_cache
    _upstream_tools_cache = None

    try:
        tools = await get_upstream_tools()
        return json_result(
            {
                "status": "success",
                "message": f"Cache refreshed. Found {len(tools)} tools.",
                "tools": [t.get("name") for t in tools],
            }
        )
    except Exception as e:
        return json_result({"status": "error", "message": str(e)}, is_error=True)
