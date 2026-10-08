---
name: jamf-mcp-development
description: Implement or review Jamf MCP tools, registration, result contracts and remote authorization.
---

Read [Development](../../../docs/DEVELOPMENT.md) and
[Architecture](../../../docs/ARCHITECTURE.md) for the current repository contract.
Use `@jamf_tool` in `src/jamf_mcp/tools/_registry.py`; product identity is derived
from the tool's module. Preserve tenant JSON results and native docs MCP results.

When changing authorization, verify both catalogue exposure and direct-call
rejection through the real MCP interface. Read-only annotations drive remote
scope selection, so match them to actual tenant operations. Credential generation
remains local-only. Follow [Remote validation](../../../docs/REMOTE_VALIDATION.md)
when assessing deployment evidence.

Run `./scripts/check.sh` for validation. Update tool counts and exact privileges
when the catalogue changes. For live reads, follow
[Local Docker](../../../docs/LOCAL_DOCKER.md) and report each product separately.
