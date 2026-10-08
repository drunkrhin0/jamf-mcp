# Jamf MCP

One MCP connection for Jamf Pro, Platform, Protect, Security Cloud and API documentation.

An independently maintained fork of the [original Jamf MCP server](https://github.com/Jamf-Concepts/mcp-hub).

## Install

Tell your agent:

> Install Jamf MCP from https://github.com/drunkrhin0/jamf-mcp. Follow docs/INSTALLATION.md, configure it for my MCP client, and start it in read-only mode. Help me set up the Jamf products I need.

The server starts without credentials. You can use its setup tools and public
API documentation before connecting a Jamf tenant. Management tools need
credentials for the products you choose. Keep secrets in your local environment
or password manager.

For manual setup, follow [Installation](docs/INSTALLATION.md). For a local
service with TLS and reader-only access, use [Docker Compose](docs/LOCAL_DOCKER.md).

## What it supports

| Product | Capabilities |
| --- | --- |
| Jamf Pro | Inventory, groups, policies, profiles, apps and device reports |
| Jamf Platform | Read-only Blueprints, compliance benchmarks and DDM reports |
| Jamf Protect | Enrolled computers, alerts and detection rules |
| Jamf Security Cloud | Device risk status and overrides |
| API documentation | Endpoint search, details and schemas without tenant credentials |

Once connected, try:

- "What's the setup status?"
- "Find all computers running macOS 15."
- "Look up the API documentation for computer inventory."

See [Tools](docs/TOOLS.md) for the full catalogue. Local Pro and documentation
reads have been verified. Other products and external hosting still need live
validation; see [validation status](docs/LOCAL_DOCKER.md#current-validation-status).

## Guides

- [Installation](docs/INSTALLATION.md): credentials and MCP client configuration.
- [Docker Compose](docs/LOCAL_DOCKER.md): local service, 1Password and live checks.
- [Platform setup](docs/PLATFORM_SETUP.md): Blueprint and benchmark permissions.
- [Documentation tools](docs/DOCUMENTATION.md): integrated API lookup.
- [Remote deployment](docs/REMOTE_VALIDATION.md): authentication and hosting checks.
- [Development](docs/DEVELOPMENT.md): tests, dependencies and contributions.
- [Container security patches](docker/SECURITY_PATCHES.md): backports and maintenance.

## License

[MIT](LICENSE). Original copyright 2026 Jamf Software LLC.
