"""Check a deployed MCP endpoint without executing Jamf mutations."""

import argparse
import asyncio
import os
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from mcp.server.auth.routes import build_resource_metadata_url

from jamf_mcp.remote import (
    RemoteAuthConfig,
    remote_auth_mode_from_env,
    validate_remote_resource_url,
)

# Fixed read-only calls; caller-supplied tool names/arguments are never executed.
BACKEND_READS = {
    "jamf_platform": ("jamf_platform_get_blueprints", {"page": 0, "page_size": 1}),
    "jamf_platform_compliance": ("jamf_platform_get_benchmarks", {}),
    "jamf_pro": ("jamf_get_computer", {"page": 0, "page_size": 1}),
    "jamf_protect": ("jamf_protect_list_computers", {"limit": 1}),
    "jamf_security": ("jamf_get_risk_devices", {"page": 0, "page_size": 1}),
}


@dataclass(frozen=True)
class BearerProbeConfig:
    """Public endpoint configuration; the probe never loads server token records."""

    resource_url: str


async def validate(
    config: RemoteAuthConfig | BearerProbeConfig,
    token: str | None,
    backends: Sequence[str] = (),
) -> None:
    """Verify discovery, admission, and optional read-only MCP calls.

    Args:
        config: The chosen HTTPS endpoint and OAuth issuer, if applicable.
        token: Optional access token supplied through the environment.
        backends: Explicitly selected products for live read-only backend checks.
    """
    if any(backend not in BACKEND_READS for backend in backends):
        raise ValueError("Unknown backend selection")
    if backends and not token:
        raise ValueError("Backend reads require JAMF_MCP_VALIDATION_TOKEN")
    meta = {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "jamf-validation", "version": "1"},
        "io.modelcontextprotocol/clientCapabilities": {},
    }
    headers = {
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2026-07-28",
        "Mcp-Method": "server/discover",
    }
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        if isinstance(config, RemoteAuthConfig):
            metadata = await client.get(str(build_resource_metadata_url(config.resource_url)))
            metadata.raise_for_status()
            document = metadata.json()
            if document.get("resource") != config.resource_url:
                raise ValueError("Resource metadata does not identify the configured MCP endpoint")
            issuers = document.get("authorization_servers")
            if (
                not isinstance(issuers, list)
                or not all(isinstance(issuer, str) for issuer in issuers)
                or config.issuer_url not in issuers
            ):
                raise ValueError("Resource metadata does not advertise the configured issuer")
            if document.get("scopes_supported") != ["jamf:read"]:
                raise ValueError("Initial discovery must advertise only the basic read scope")
            print("PASS protected-resource discovery")
        response = await client.post(
            config.resource_url,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "server/discover",
                "params": {"_meta": meta},
            },
        )
        challenge = response.headers.get("www-authenticate", "")
        if response.status_code != 401 or 'scope="jamf:read"' not in challenge:
            raise ValueError("Unauthenticated requests must receive a read-scope 401 challenge")
        print("PASS unauthenticated admission")
        if not token:
            print("PENDING authenticated checks: set JAMF_MCP_VALIDATION_TOKEN")
            return
        calls = [
            (2, "server/discover", {}),
            (3, "tools/list", {}),
            (4, "tools/call", {"name": "jamf_get_setup_status", "arguments": {}}),
        ]
        for backend in dict.fromkeys(backends):
            name, arguments = BACKEND_READS[backend]
            calls.append((len(calls) + 2, "tools/call", {"name": name, "arguments": arguments}))
        for request_id, method, params in calls:
            label = params.get("name", method)
            request_headers = {**headers, "Authorization": f"Bearer {token}", "Mcp-Method": method}
            if "name" in params:
                request_headers["Mcp-Name"] = params["name"]
            response = await client.post(
                config.resource_url,
                headers=request_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": {**params, "_meta": meta},
                },
            )
            # Report status only; response bodies may contain private tenant data.
            if response.status_code != 200:
                raise ValueError(f"Authenticated {label} returned HTTP {response.status_code}")
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
                raise ValueError(f"Invalid modern JSON-RPC response for {label}")
            result = payload.get("result", {})
            if (
                payload.get("id") != request_id
                or not isinstance(result, dict)
                or result.get("resultType") != "complete"
            ):
                raise ValueError(f"Invalid modern JSON-RPC response for {label}")
            if "error" in payload or result.get("isError"):
                raise ValueError(f"Authenticated {label} failed")
            if method == "server/discover" and "2026-07-28" not in result.get(
                "supportedVersions", []
            ):
                raise ValueError("Discovery does not advertise the requested protocol version")
            if method == "tools/call":
                structured = result.get("structuredContent")
                if not isinstance(structured, dict) or structured.get("success") is not True:
                    raise ValueError(
                        f"{label} did not return a successful structured result"
                    )
            if method == "tools/list":
                tools = result.get("tools", [])
                if not tools:
                    raise ValueError("Remote catalogue is empty")
                if isinstance(config, RemoteAuthConfig) and any(
                    not any(
                        scheme.get("type") == "oauth2" and "jamf:read" in scheme.get("scopes", [])
                        for scheme in tool.get("securitySchemes", [])
                    )
                    for tool in tools
                ):
                    raise ValueError("Tool catalogue is missing OAuth declarations")
                if any(tool.get("name") == "jamf_create_api_client_credentials" for tool in tools):
                    raise ValueError("Remote catalogue exposes credential generation")
            print(f"PASS authenticated {label}")
        if isinstance(config, RemoteAuthConfig):
            print(
                "PENDING host validation: complete OAuth linking and scope step-up "
                "in the chosen host"
            )
        else:
            print("PENDING gateway validation: check gateway access policy and scope denials")


def main() -> None:
    """Run the deployment probe using public configuration and an optional token."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("JAMF_MCP_RESOURCE_URL"))
    parser.add_argument("--issuer", default=os.environ.get("JAMF_MCP_OAUTH_ISSUER_URL"))
    parser.add_argument(
        "--auth-mode",
        choices=["oauth", "bearer"],
        default=os.environ.get("JAMF_MCP_REMOTE_AUTH_MODE", "oauth"),
    )
    parser.add_argument(
        "--backend",
        action="append",
        choices=list(BACKEND_READS),
        default=[],
        help="Opt in to a live read through MCP for this product; repeat for each product",
    )
    args = parser.parse_args()
    try:
        mode = remote_auth_mode_from_env({"JAMF_MCP_REMOTE_AUTH_MODE": args.auth_mode})
        config: RemoteAuthConfig | BearerProbeConfig
        if mode == "oauth":
            config = RemoteAuthConfig.from_env(
                {
                    "JAMF_MCP_RESOURCE_URL": args.url or "",
                    "JAMF_MCP_OAUTH_ISSUER_URL": args.issuer or "",
                }
            )
        else:
            config = BearerProbeConfig(validate_remote_resource_url(args.url or ""))
        if not urlsplit(config.resource_url).path:
            raise ValueError("The public URL must include its MCP endpoint path")
        asyncio.run(validate(config, os.environ.get("JAMF_MCP_VALIDATION_TOKEN"), args.backend))
    except (ValueError, httpx.HTTPError) as error:
        parser.exit(1, f"Validation failed: {error}\n")


if __name__ == "__main__":
    main()
