# Available tools

Complete reference for all MCP tools organized by Jamf product.

## Contents

- [Documentation tools](#documentation-tools)
- [Setup tools](#setup-tools) (always available)
- [Jamf Pro](#jamf-pro)
  - [Device management](#device-management)
  - [Groups](#groups)
  - [Configuration & policies](#configuration--policies)
  - [App deployment](#app-deployment)
  - [Inventory & organization](#inventory--organization)
  - [API administration](#api-administration)
- [Jamf Platform](#jamf-platform)
- [Jamf Protect](#jamf-protect)
  - [Alerts](#alerts)
  - [Computers](#computers)
  - [Analytics](#analytics)
- [Jamf Security Cloud](#jamf-security-cloud)
  - [Risk management](#risk-management)
- [Usage examples](#usage-examples)
- [API reference](#api-reference)

---

# Documentation tools

These nine read-only tools share the main MCP endpoint and need no tenant
credentials. They connect to the public Jamf docs service when called. Include
`docs` in explicit product filters; remote callers require `jamf:read`.

| Tool | Description |
|------|-------------|
| `list_jamf_api_tools` | Discover approved upstream documentation tools and schemas |
| `list_available_specs` | List available API specifications |
| `search_jamf_api` | Search endpoints across specifications |
| `list_api_endpoints` | List endpoints for a specification |
| `get_endpoint_details` | Read endpoint parameters and security requirements |
| `get_request_body_schema` | Read a documented request schema |
| `get_response_schema` | Read a documented response schema |
| `call_jamf_docs_tool` | Call an approved documentation operation with JSON arguments |
| `refresh_jamf_docs_cache` | Refresh the cached upstream tool catalogue |

See [Documentation lookup](DOCUMENTATION.md) for examples and result behavior.

---

# Setup tools

These tools are always available, even with no credentials configured. Use them to check configuration status and get setup instructions.

| Tool | Description |
|------|-------------|
| `jamf_get_setup_status` | Check which products are configured and how many tools are available |
| `jamf_configure_help` | Get step-by-step setup instructions for any product |

Use these tools for:

- First time starting the server
- Checking which products are configured
- Getting setup instructions for a new product
- Troubleshooting configuration issues

Example:

```
"What's the setup status?" -> jamf_get_setup_status()
"How do I configure Jamf Protect?" -> jamf_configure_help(product="jamf_protect")
"Show me all setup instructions" -> jamf_configure_help(product="all")
```

---

# Jamf Pro

Core device management tools for macOS, iOS/iPadOS, and tvOS devices.

## Device management

| Tool | Description |
|------|-------------|
| `jamf_get_computer` | Get computer info by ID, serial number, or name; list `sections=["GENERAL", "HARDWARE"]` for names and serials without full details |
| `jamf_update_computer` | Update computer inventory fields and extension attributes |
| `jamf_get_ddm_status` | Read latest Pro DDM status using `general.managementId`; optional status-item key |
| `jamf_get_device_compliance_information` | Read conditional-access compliance for a numeric Pro computer/mobile ID; explicitly not CIS benchmark results |
| `jamf_get_mobile_device` | Get mobile device info by ID, serial number, or name |
| `jamf_update_mobile_device` | Update mobile device inventory fields |
| `jamf_get_user` | Get user info by ID, username, or email |
| `jamf_update_user` | Update user record fields |

## Groups

| Tool | Description |
|------|-------------|
| `jamf_get_smart_groups` | List smart groups or get details with criteria |
| `jamf_create_smart_group` | Create a new smart group with criteria |
| `jamf_get_static_groups` | List static groups or get members |
| `jamf_create_static_group` | Create a new static group with members |

## Configuration & policies

| Tool | Description |
|------|-------------|
| `jamf_get_policies` | Get policies with optional filtering |
| `jamf_get_computer_configuration_profiles` | Get macOS configuration profiles |
| `jamf_get_mobile_device_configuration_profiles` | Get iOS/iPadOS configuration profiles |
| `jamf_get_prestages` | Get computer or mobile device prestage enrollments |

## App deployment

| Tool | Description |
|------|-------------|
| `jamf_get_app_installer_titles` | Get available apps from Jamf App Catalog |
| `jamf_get_app_installer_deployments` | Get App Installer deployment configurations |
| `jamf_create_app_installer_deployment` | Create a new App Installer deployment |
| `jamf_get_app_installers` | Get App Installers with deployment status |
| `jamf_get_mac_apps` | Get Mac App Store / VPP app deployments |
| `jamf_get_mobile_device_apps` | Get iOS/iPadOS app deployments |
| `jamf_get_ebooks` | Get eBook deployments |
| `jamf_get_restricted_software` | Get restricted software configurations |
| `jamf_get_patch_policies` | Get patch management policies |

## Inventory & organization

| Tool | Description |
|------|-------------|
| `jamf_get_scripts` | Get scripts used in policies |
| `jamf_get_extension_attributes` | Get extension attribute definitions |
| `jamf_create_extension_attribute` | Create new extension attributes |
| `jamf_get_categories` | Get categories for organizing objects |
| `jamf_create_category` | Create a new category |
| `jamf_get_buildings` | Get building locations |
| `jamf_get_departments` | Get departments |
| `jamf_get_printers` | Get printers or printer details by ID |
| `jamf_create_printer` | Create a new printer |
| `jamf_update_printer` | Update an existing printer by ID |

## API administration

| Tool | Description |
|------|-------------|
| `jamf_get_api_role_privileges` | Get available privileges for API roles |
| `jamf_get_api_roles` | List API roles or get specific role details |
| `jamf_create_api_role` | Create a new API role with privileges |
| `jamf_get_api_integrations` | List API integrations |
| `jamf_create_api_integration` | Create a new API integration (client) |
| `jamf_create_api_client_credentials` | Generate OAuth credentials for an integration |
| `jamf_create_computer_update_api_client` | Create API role + client for computer updates |

---

# Jamf Platform

Requires a separate [Jamf Account Platform integration](PLATFORM_SETUP.md).
All seven tools are read-only and use the regional Platform gateway.

| Tool | Description | Permission |
| --- | --- | --- |
| `jamf_platform_get_blueprints` | List Blueprints or get a definition by UUID | `blueprints:read` |
| `jamf_platform_get_benchmarks` | List benchmarks or get a configuration by string ID | `compliance-benchmarks:read` |
| `jamf_platform_get_benchmark_rules` | Rule pass/fail/unknown counts | `compliance-benchmarks:read` |
| `jamf_platform_get_benchmark_devices` | Device results for a required `rule_id`; optional `rule_result` | `compliance-benchmarks:read` |
| `jamf_platform_get_benchmark_compliance` | Overall benchmark compliance percentage | `compliance-benchmarks:read` |
| `jamf_platform_get_declarations` | Declarations for a Platform device UUID, or devices for a declaration identifier; required `filter` | `declarations:read` |
| `jamf_platform_get_device_channels` | DDM reporting channels for a Platform device UUID | `declarations:read` |

Blueprint lists, rule statistics, device results and declaration reports are
paginated. Benchmark lists have no pagination parameters. Declaration reports
exclude pending declarations; an empty report cannot confirm full deployment.
The component catalogue, deployment and inventory ID mapping are not exposed.

---

# Jamf Protect

Endpoint security tools for threat detection and response. Requires [Jamf Protect configuration](INSTALLATION.md#jamf-protect-optional).

## Alerts

| Tool | Description |
|------|-------------|
| `jamf_protect_get_alert` | Get details of a specific security alert by UUID |
| `jamf_protect_list_alerts` | List security alerts with filtering options |

## Computers

| Tool | Description |
|------|-------------|
| `jamf_protect_get_computer` | Get Protect-enrolled computer details by UUID |
| `jamf_protect_list_computers` | List computers enrolled in Jamf Protect |

## Analytics

| Tool | Description |
|------|-------------|
| `jamf_protect_get_analytic` | Get details of a specific analytic (detection rule) |
| `jamf_protect_list_analytics` | List all analytics (detection rules) |

---

# Jamf Security Cloud

Device risk management via the RISK API. Requires [Security Cloud configuration](INSTALLATION.md#jamf-security-cloud-optional).

## Risk management

| Tool | Description |
|------|-------------|
| `jamf_get_risk_devices` | Get device risk status |
| `jamf_override_device_risk` | Override risk level for specific devices |

---

# Usage examples

| Task | Example Prompt |
|------|---------------|
| Find devices | "Find all computers in the Engineering department" |
| Look up by serial | "Get the computer with serial number EXAMPLE-SERIAL" |
| Update inventory | "Set asset tag 'ENG-001' on computer ID 42" |
| Create smart group | "Create a smart group for macOS 14+ devices" |
| Create static group | "Create a static group 'Executives' with computer IDs 10, 15, 22" |
| View policies | "Show all policies in the Security category" |
| List alerts | "Show me recent Jamf Protect alerts" |
| Check risk | "What devices have elevated risk scores?" |

---

# API reference

This server uses multiple Jamf APIs:

| Product | API | Endpoint Pattern |
|---------|-----|------------------|
| **Jamf Pro** | Classic | `/JSSResource/...` |
| **Jamf Pro** | v1 | `/api/v1/...` |
| **Jamf Pro** | v2 | `/api/v2/...` |
| **Jamf Pro** | v3 | `/api/v3/...` |
| **Jamf Protect** | GraphQL | `/graphql` |
| **Security Cloud** | RISK API | `/v1/risk/...` |

For complete API documentation:
- [Jamf Pro API](https://developer.jamf.com/)
- [Jamf Protect API](https://learn.jamf.com/en-US/bundle/jamf-protect-documentation/page/Jamf_Protect_API.html)
- [Jamf Security API](https://developer.jamf.com/jamf-security)
