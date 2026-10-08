# Copyright 2026, Jamf Software LLC
"""Tool registry for Jamf MCP Server.

This module provides a decorator-based registration system for MCP tools.
Tools decorated with @jamf_tool are automatically collected and can be
registered with the MCPServer server using register_all().

Usage:
    # In tool modules:
    from ._registry import jamf_tool

    @jamf_tool
    async def jamf_get_something(...) -> str:
        '''Docstring becomes MCP tool description.'''
        # implementation

    # In server.py:
    from .tools import register_all_tools
    register_all_tools(mcp)
"""

import json
from collections.abc import Callable, Mapping
from enum import Enum
from functools import wraps
from typing import Any

from mcp import MCPError
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp_types import CallToolResult, TextContent, ToolAnnotations


class ToolType(Enum):
    API = "api"
    COMPLEX = "complex"


# Registry of all MCP tools with their type
# List of tuples: (function, tool_type)
_tools: list[tuple[Callable, ToolType]] = []
_annotations: dict[Callable, ToolAnnotations] = {}
PRODUCT_ALIASES = {
    "docs": "jamf_docs",
    "jamf_docs": "jamf_docs",
    "platform": "jamf_platform",
    "jamf_platform": "jamf_platform",
    "pro": "jamf_pro",
    "protect": "jamf_protect",
    "security": "jamf_security_cloud",
    "risk": "jamf_security_cloud",
    "jamf_pro": "jamf_pro",
    "jamf_protect": "jamf_protect",
    "jamf_security_cloud": "jamf_security_cloud",
}


def jamf_tool(
    func_or_type: Callable | None = None,
    tool_type: ToolType = ToolType.API,
    *,
    read_only: bool = False,
    destructive: bool = True,
) -> Callable:
    """Decorator to register a function as an MCP tool.

    Can be used as @jamf_tool or @jamf_tool(tool_type=ToolType.COMPLEX).

    The decorated function will be automatically registered with the
    MCPServer server when register_all() is called.

    The function's docstring becomes the MCP tool description shown to LLMs.

    Args:
        func_or_type: Decorated function, or None when supplying options.
        tool_type: Catalogue filter category.
        read_only: True only when the tool cannot change state.
        destructive: False for purely additive writes. Ignored for read-only tools.

    """

    def _decorator(func: Callable) -> Callable:
        _tools.append((func, tool_type))
        _annotations[func] = ToolAnnotations(
            read_only_hint=read_only,
            destructive_hint=not read_only and destructive,
            idempotent_hint=read_only,
            open_world_hint=False,
        )
        return func

    if func_or_type is None:
        # Called as @jamf_tool(tool_type=...)
        return _decorator
    elif callable(func_or_type):
        # Called as @jamf_tool without arguments
        return _decorator(func_or_type)
    else:
        # Support the legacy positional tool type.
        tool_type = func_or_type
        return _decorator


def get_tool_product(func: Callable) -> str:
    """Determine which product a tool belongs to based on its module.

    Returns:
        One of: jamf_pro, jamf_platform, jamf_protect, jamf_security_cloud, jamf_docs, setup
    """
    module_name = func.__module__

    if module_name.endswith(".docs"):
        return "jamf_docs"
    elif module_name.endswith(".platform"):
        return "jamf_platform"
    elif "protect" in module_name:
        return "jamf_protect"
    elif "risk" in module_name or "security" in module_name:
        return "jamf_security_cloud"
    elif "setup" in module_name:
        return "setup"

    # default to Jamf Pro for other tools in tools package
    return "jamf_pro"


def register_all(
    mcp,
    tool_filter: str | None = None,
    allowed_products: list[str] | None = None,
    *,
    excluded_tools: frozenset[str] = frozenset(),
    tool_metadata: Mapping[str, dict[str, Any]] | None = None,
) -> None:
    """Register all decorated tools with the MCPServer server.

    Args:
        mcp: The MCPServer server instance to register tools with.
        tool_filter: Optional filter string ('api' or 'complex').
                    If None or 'all', registers all tools.
        allowed_products: Optional list of product names to register tools for.
                         If None, registers all products.
                         Valid values: PRODUCT_ALIASES keys, including docs and jamf_docs.
                         Note: 'setup' tools are always registered.
        excluded_tools: Tool names disabled by the deployment's exposure policy.
        tool_metadata: Optional host metadata keyed by tool name.
    """
    tool_filter = (tool_filter or "all").lower()
    if tool_filter not in {"all", "api", "complex"}:
        raise ValueError(f"Unknown tool filter: {tool_filter}")
    products = None
    if allowed_products:
        try:
            products = {PRODUCT_ALIASES[p.lower()] for p in allowed_products}
        except KeyError as error:
            raise ValueError(f"Unknown product: {error.args[0]}") from error

    exposed_names: set[str] = set()
    for func, t_type in _tools:
        if func.__name__ in excluded_tools:
            continue
        product = get_tool_product(func)
        if product != "setup":
            if tool_filter != "all" and t_type.value != tool_filter:
                continue
            if products is not None and product not in products:
                continue
        exposed_names.add(func.__name__)
        mcp.tool(
            annotations=_annotations[func],
            structured_output=False,
            meta=tool_metadata.get(func.__name__) if tool_metadata else None,
        )(_mcp_adapter(func))


    async def validate_tool_name(
        ctx: ServerRequestContext[Any, Any], call_next: CallNext
    ) -> HandlerResult:
        """Keep catalogue lookup failures as protocol errors before execution."""
        if ctx.method == "tools/call":
            require_known_tool_name(ctx.params, exposed_names)
        return await call_next(ctx)

    mcp.middleware.append(validate_tool_name)


def require_known_tool_name(params: object, names: set[str] | frozenset[str]) -> str:
    """Validate a tool lookup without confusing it with execution or OAuth errors.

    Args:
        params: The incoming tools/call parameters.
        names: Tool names exposed by this catalogue.

    Returns:
        The validated tool name.

    Raises:
        MCPError: When the name is malformed or absent from the catalogue.
    """
    name = params.get("name") if isinstance(params, Mapping) else None
    if not isinstance(name, str):
        raise MCPError(-32602, "Tool name must be a string")
    if name not in names:
        raise MCPError(-32602, f"Unknown tool: {name}")
    return name


def _mcp_adapter(func: Callable) -> Callable:
    """Expose the existing JSON contract as structured MCP results.

    Native MCP results are preserved, including upstream content and metadata.
    Direct Python callers of tenant tools retain the JSON string interface. MCP callers receive
    the same text, structured data, and the protocol's execution error flag.
    """

    @wraps(func)
    async def call(**kwargs: Any) -> CallToolResult:
        response = await func(**kwargs)
        if isinstance(response, CallToolResult):
            return response
        data = json.loads(response)
        return CallToolResult(
            content=[TextContent(type="text", text=response)],
            structured_content=data,
            is_error=isinstance(data, dict) and data.get("success") is False,
        )

    return call


def get_registered_tools() -> list[tuple[Callable, ToolType]]:
    """Get list of all registered tool functions with their types.

    Useful for introspection and testing.
    """
    return _tools.copy()


def get_tool_annotations(func: Callable) -> ToolAnnotations | None:
    """Return the registered safety hints used to authorize remote tools."""
    annotation = _annotations.get(func)
    return annotation.model_copy(deep=True) if annotation is not None else None
