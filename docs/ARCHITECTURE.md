# Jamf MCP architecture

Jamf MCP serves Jamf Pro, Platform, Protect, Security Cloud and documentation
through one endpoint. `src/jamf_mcp/server.py` builds the official SDK's
`MCPServer`, initializes configured tenant clients and registers the catalogue.
The Python import is `jamf_mcp`. The command and advertised server name are
`jamf-mcp`.

## Catalogue and results

`@jamf_tool` in `tools/_registry.py` collects functions, their category and safety
annotations. `tools/__init__.py` imports tool modules and registers selected
products. Setup tools bypass product and category filters. Documentation is the
`docs` product in the `api` category. The default catalogue has 68 tools.

Tenant tools return JSON text with a `success` field. The adapter adds structured
data and sets MCP `isError` when execution fails. Native documentation results
retain upstream content and metadata. Unknown local tool names remain JSON-RPC
lookup errors. [Documentation](DOCUMENTATION.md) explains schema extraction and
the fixed upstream allowlist, which excludes `execute-request`.

## Clients and credentials

Pro uses its tenant API role/client. Platform uses a separate regional Jamf Account
integration and environment UUID. Protect and Security Cloud each use their own
credentials. Documentation uses the public developer MCP service and receives no
inbound token or tenant credentials. Clients connect lazily; discovery and startup
do not require documentation service availability.

## Transport and authorization

Local stdio is the default. Protected Streamable HTTP supports OAuth JWT
verification or scoped bearer identities. Every remote tool receives a scope
policy derived from its registered safety annotations. Reads require `jamf:read`;
writes additionally require `jamf:write`; API administration also requires
`jamf:admin`. Credential generation is disabled remotely. `--read-only` removes
write tools from the catalogue. Annotations alone do not authorize execution.

Backend credentials stay on the server and are shared by its authorized callers.
An external deployment therefore needs an access policy appropriate to that
configured tenant. [Remote validation](REMOTE_VALIDATION.md) describes host OAuth
and gateway checks. Offline tests do not establish those external behaviors.

The local [Compose deployment](LOCAL_DOCKER.md) binds only to localhost, uses TLS,
accepts a reader token and exposes Pro, Platform and docs. Record live results
per product; setup status alone is not evidence of accepted backend credentials.
