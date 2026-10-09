---
name: jamf-inventory-report
description: Report Jamf Pro computer or mobile-device inventory, including fleet counts, OS versions and device lookups.
---

Use the selected Jamf plugin connection in this chat. If its tools are missing,
report the connection as unavailable and ask the user to connect/enable it.
A terminal or Docker probe does not verify this plugin connection.


Use the Jamf read-only MCP connection. Discover its available tools and call
`jamf_get_setup_status` to check configuration. Configuration status alone does
not prove tenant access; establish access with the requested inventory read.
If Pro is unavailable, use `jamf_configure_help(product="jamf_pro")` and report
that inventory could not be read. Keep credentials out of chat.

Clarify whether an ambiguous device request concerns computers, mobile devices
or users before reading inventory. Use `jamf_get_computer` for computers and
`jamf_get_mobile_device` for mobile devices. Prefer an exact serial or numeric
Pro ID for a device lookup; name searches can match several devices. Resolve
multiple matches with the user before selecting a device.

For computer lists, request only the sections needed: GENERAL and HARDWARE for
names and serials, adding OPERATING_SYSTEM for OS reporting. A computer_id
lookup returns full details and does not accept sections. Use the discovered
schema for supported parameters. Apply unsupported filters to retrieved data
and disclose that filtering was local.

Follow pagination until the requested population is covered or a user-specified
limit is reached. Distinguish upstream totalCount from retrieved rows and local
matches. If a page fails, report partial coverage; an error is not an empty fleet.

Return the requested fields and counts, identifying device type, filters,
coverage and missing values. Include serials, user details or other personal
fields only when needed for the request. Label stale inventory when timestamps
are available. A successful inventory read establishes access to Pro only.
