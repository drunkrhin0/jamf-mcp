---
name: jamf-compliance-assessment
description: Assess Jamf Platform benchmark compliance or investigate a device's Pro conditional-access and DDM reports.
---

Use the selected Jamf plugin connection in this chat. If its tools are missing,
report the connection as unavailable and ask the user to connect/enable it.
A terminal or Docker probe does not verify this plugin connection.


Use the Jamf read-only MCP connection and discover the available tool schemas.
Call `jamf_get_setup_status`, then verify access with the relevant report read.
If the product is unavailable, use `jamf_configure_help` for that product and
report the missing access. Keep credentials outside chat.

Select the report that answers the request. CIS/NIST benchmark assessments use
Jamf Platform's separate environment integration. Pro conditional-access
records and DDM status answer different questions and do not substitute for
benchmark results.

For benchmarks, use `jamf_platform_get_benchmarks` to identify the requested
benchmark; ask which one if several match. Definitions describe configured
rules. Use `jamf_platform_get_benchmark_compliance` for the reported aggregate
percentage and `jamf_platform_get_benchmark_rules` for assessed rule counts.
Drill into relevant rules with `jamf_platform_get_benchmark_devices`, supplying
both benchmark_id and rule_id. Preserve PASSED, FAILED and UNKNOWN results.
Follow rule and device pagination for the requested scope and label partial
coverage. Benchmark lists have no pagination parameters.

Platform device IDs are not numeric Pro inventory IDs. There is no exposed
inventory ID mapping; use only identities established by returned evidence and
report unmatched devices rather than guessing a join.

For conditional access, clarify computer versus mobile device and use
`jamf_get_device_compliance_information` with the numeric Pro device_id and
matching device_type. For Pro DDM, use `jamf_get_ddm_status` with inventory's
general.managementId. Neither an empty conditional-access array nor an empty
DDM report establishes a compliance verdict.

Return the benchmark/report identity, population and retrieval coverage, source
counts or percentage, unknowns and failures. Keep aggregate percentage separate
from per-rule counts; do not recalculate a fleet score from incomplete pages.
A failed read is unavailable evidence, not a pass or zero failures. Propose
follow-up investigation or remediation for review without executing changes.
