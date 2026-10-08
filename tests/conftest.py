"""Isolate local tests from live Jamf tenants and credentials."""

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
pytest_plugins = ["backend_helpers"]


@pytest.fixture(autouse=True)
def isolated_clients(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ensure tests cannot inherit configured production clients."""
    from jamf_mcp.tools._common import (
        PRODUCT_CONFIG,
        set_client,
        set_platform_client,
        set_protect_client,
        set_security_client,
    )

    for product in PRODUCT_CONFIG.values():
        for variable in product["env_vars"]:
            monkeypatch.delenv(variable, raising=False)
    for variable in (
        "JAMF_MCP_REMOTE_AUTH_MODE",
        "JAMF_MCP_BEARER_TOKENS_JSON",
        "JAMF_MCP_OAUTH_ISSUER_URL",
        "JAMF_MCP_OAUTH_AUDIENCE",
        "JAMF_MCP_RESOURCE_URL",
        "JAMF_MCP_TRANSPORT",
        "JAMF_MCP_HOST",
        "JAMF_MCP_PORT",
        "JAMF_MCP_VALIDATION_TOKEN",
    ):
        monkeypatch.delenv(variable, raising=False)
    set_client(None)
    set_protect_client(None)
    set_security_client(None)
    set_platform_client(None)
    yield
    set_client(None)
    set_protect_client(None)
    set_security_client(None)
    set_platform_client(None)
