# Copyright 2026, Jamf Software LLC
"""Task guidance for Jamf MCP clients."""


def register_prompts(mcp):
    """Register task prompts under their existing client-facing names."""

    @mcp.prompt("security-researcher")
    def security_researcher() -> str:
        """Review fleet security evidence."""
        return (
            "Check configured products and use the available inventory, Protect alert and "
            "risk-reporting tools to investigate fleet security. Report the evidence and "
            "untested products. A successful API read alone does not establish device safety."
        )

    @mcp.prompt("it-administrator")
    def it_administrator() -> str:
        """Inspect inventory and plan an authorized change."""
        return (
            "Inspect inventory, groups, policies and enrollment settings with the available "
            "tools. Clarify ambiguous computer, mobile-device or user requests. Before a broad "
            "deployment, inspect its detailed scope, explain the affected population and "
            "obtain explicit confirmation. Prefer a phased rollout."
        )

    @mcp.prompt("compliance-officer")
    def compliance_officer() -> str:
        """Assess compliance using the appropriate report."""
        return (
            "Use Platform benchmark rule and device results for CIS/NIST assessments. "
            "Pro conditional-access records and DDM status are separate reports. Preserve "
            "pass, fail and unknown results; empty reports establish no compliance verdict. "
            "Keep Platform device UUIDs distinct from numeric Pro inventory IDs."
        )

    @mcp.prompt("support-technician")
    def support_technician() -> str:
        """Investigate a device support issue."""
        return (
            "Identify whether the request concerns a computer or mobile device, then inspect "
            "its inventory, relevant profile definitions and available DDM status. Explain "
            "what the returned evidence establishes. Propose only actions supported by the "
            "discovered tool catalogue and authorized by the user."
        )
