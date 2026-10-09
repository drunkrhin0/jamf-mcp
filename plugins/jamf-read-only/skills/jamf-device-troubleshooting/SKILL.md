---
name: jamf-device-troubleshooting
description: Investigate a Jamf-managed computer or mobile device using inventory, configuration profiles and DDM reporting.
---

Use the selected Jamf plugin connection in this chat. If its tools are missing,
report the connection as unavailable and ask the user to connect/enable it.
A terminal or Docker probe does not verify this plugin connection.


Use the Jamf read-only MCP connection and its discovered tool schemas. Check
`jamf_get_setup_status`, then verify access with the device read. Use
`jamf_configure_help` for missing product configuration; keep secrets outside
chat. Configuration status is not proof of upstream access.

Clarify computer versus mobile device when ambiguous. Resolve the target with
an exact serial or numeric Pro ID using `jamf_get_computer` or
`jamf_get_mobile_device`. Name searches may return multiple matches; confirm
which device before investigating. Keep numeric Pro IDs, Pro management IDs
and Platform device UUIDs distinct.

Inspect inventory relevant to the symptom, then read the matching computer or
mobile configuration profile definitions. A profile definition or deployment
scope does not establish installation on a particular device. Use actual device
inventory or reporting evidence to describe applied state.

For Pro DDM status, pass inventory's general.managementId as
`client_management_id` to `jamf_get_ddm_status`. If that identifier is absent,
report the missing evidence. For Platform declaration or channel reporting,
require a known Platform device UUID; the tools do not expose Pro-to-Platform
ID mapping. `jamf_platform_get_declarations` requires a nonempty filter and
reports declarations already on devices, excluding pending declarations.
An empty report does not prove that all assigned settings arrived.

If deployment impact is relevant, read each deployment's detailed scope before
explaining the affected population. Lists can contain only scope IDs.

Return findings tied to the device and source tool, distinguish observed state
from hypotheses, and list missing evidence or the next useful read. Propose
remediation for review when warranted. This workflow performs reads only; it
does not update inventory, send commands, or deploy settings.
