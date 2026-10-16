# Jamf MCP

Connect a local MCP client to Jamf Pro, Platform, Protect, Security Cloud and API documentation.

An independently maintained fork of the [original Jamf MCP server](https://github.com/Jamf-Concepts/mcp-hub).

## Install

Tell your agent:

> Install Jamf MCP from https://github.com/drunkrhin0/jamf-mcp. Follow docs/INSTALLATION.md, configure it for my MCP client, and start it in read-only mode. Help me set up the Jamf products I need.

Requires Python 3.10+ and the MCP SDK `mcp>=2.3.0,<3`.

The server starts without credentials. Setup tools and public API documentation
work before you connect a tenant. Store credentials for the products you need
in your local environment or password manager.

Follow [Installation](docs/INSTALLATION.md) for manual setup. Use
[Docker Compose](docs/DOCKER.md) for a local service with TLS and read-only
access.

This repository includes a local OpenAI plugin with skills for setup, inventory
reporting, device troubleshooting and compliance assessment. It starts the server
in read-only mode. Follow [Plugin setup](docs/OPENAI_PLUGIN.md) to install it
in a supported local host.

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

The server supports reads and writes. Only read-only workflows have been tested
against live services. The bundled plugin and Compose setup disable writes.
Local Pro inventory, device reports and documentation reads have been verified.
Platform, Protect and Security Cloud live access remains unverified. See the
[validation record](docs/VALIDATION.md) for tested paths and limits.

## Guides

- [Tools](docs/TOOLS.md): catalogue and required privileges.
- [Platform setup](docs/PLATFORM_SETUP.md): Blueprint and benchmark credentials.
- [Documentation lookup](docs/DOCUMENTATION.md): API search and schemas.
- [Development](docs/DEVELOPMENT.md): checks, dependencies and maintenance.

## License

[MIT](LICENSE). Original copyright 2026 Jamf Software LLC.
Fork contributions copyright 2026 drunkrhin0.
