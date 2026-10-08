---
name: jamf-api-lookup
description: Verify Jamf endpoints, privileges and schemas when adding or changing Jamf MCP tools.
---

Use the integrated documentation tools to discover specification titles and paths
before choosing an endpoint. Read [Documentation](../../../docs/DOCUMENTATION.md)
for their current behavior. Upstream spec titles include namespaces; paths can
omit `/api` or `/JSSResource` relative to the documented server URL. Schema tools
retain components for references; missing Classic request bodies are not inferred.

For Blueprints, benchmarks or declaration reports, read
[Platform contracts](../../../docs/PLATFORM_API_RESEARCH.md) and
[Platform setup](../../../docs/PLATFORM_SETUP.md). Keep gateway environment UUIDs
and credentials distinct from Pro tenant IDs and API roles. Do not describe
conditional-access records or DDM status as a CIS assessment.

Report the verified path, HTTP method, payload format and exact privilege. Tie
live access claims to a successful upstream read, not a schema or setup status.
