---
name: jamf-setup-status
description: Check Jamf plugin setup, connection availability and per-product configuration in ChatGPT or Codex.
---

Use the selected Jamf plugin connection in this chat. Discover its tools and
call `jamf_get_setup_status`. If its tools are unavailable, report that the
plugin connection could not be tested and ask the user to enable/connect it,
then start a fresh chat. A shell, Docker or direct SDK probe tests a different
path; use one only when the user requests that diagnostic and label it separately.

Report configuration for Pro, Platform, Protect and Security Cloud separately.
The package exposes Pro, Platform and public documentation; a configured product
may still be excluded from its catalogue. Configuration and initialized clients
alone do not verify tenant access. Use `jamf_configure_help` for missing product
configuration when available. Keep credentials outside chat.

When the user requests a live connection test, run the available read for each
configured product in scope: `jamf_get_computer(page=0, page_size=1)` for Pro,
`jamf_platform_get_blueprints(page=0, page_size=1)` for Platform Blueprints and
`jamf_platform_get_benchmarks` for benchmarks. Use discovered schemas and report
permissions separately. Documentation needs its own successful lookup; neither
setup status nor a Pro read verifies it. A failed read is unavailable evidence.

State the connection tested, successful reads, missing configuration and any
untested products. Treat setup status as complete once the plugin call returns;
add live reads only when requested. Invoking a packaged skill by itself does
not establish a working MCP connection.
