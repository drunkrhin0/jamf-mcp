# Installation and configuration

## Contents

- [Prerequisites](#prerequisites)
- [Start without credentials](#start-without-credentials)
- [Installation](#installation)
- [Run the server manually (optional)](#run-the-server-manually-optional)
- [Environment variables](#environment-variables)
  - [Jamf Pro (optional)](#jamf-pro-optional)
  - [Jamf Protect (optional)](#jamf-protect-optional)
  - [Jamf Security Cloud (optional)](#jamf-security-cloud-optional)
- [Set up API credentials](#set-up-api-credentials)
  - [Jamf Pro](#jamf-pro)
  - [Jamf Protect](#jamf-protect)
  - [Jamf Security Cloud](#jamf-security-cloud)
- [Client configuration](#client-configuration)
  - [Local stdio](#local-stdio)
  - [Remote HTTP](#remote-http)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

- Python 3.10+
- Jamf instance (optional - server starts in onboarding mode without credentials)

---

## Start without credentials

The server starts without credentials. Use the setup tools to configure products:

1. Configure your MCP client using [Client configuration](#client-configuration).
2. Restart your local stdio client to start the configured server.
3. Ask your MCP assistant for setup help:
   - "What's the setup status?" → calls `jamf_get_setup_status()`
   - "How do I configure Jamf Pro?" → calls `jamf_configure_help(product="jamf_pro")`

### How clients start the server

Local stdio MCP clients launch the server using your configured command and
arguments. Remote clients connect to a server that is already running.

### Onboarding tools

| Tool                    | Description                                   |
| ----------------------- | --------------------------------------------- |
| `jamf_get_setup_status` | Shows which products have configuration |
| `jamf_configure_help`   | Provides step-by-step setup instructions      |

These tools work without credentials. Setup status reports configuration; use
live reads to verify upstream access.

---

## Installation

Choose an installation method below. After installing, proceed to [Client configuration](#client-configuration) to set up your MCP client.

### Option 1: uv (recommended)

[uv](https://github.com/astral-sh/uv) installs the project dependencies when your
client launches the server with `uv run`.

### Option 2: pip in a virtual environment

```bash
cd /path/to/jamf-mcp
python3 -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -e .
```

### Option 3: system pip

```bash
cd /path/to/jamf-mcp
pip3 install -e .
```

---

## Run the server manually (optional)

Local stdio clients start the configured server. Run it manually to inspect startup
errors or test development changes. See [Client configuration](#client-configuration).

```bash
# Using uv
uv run jamf-mcp

# Using venv
source venv/bin/activate && jamf-mcp

# Using system pip
python3 -m jamf_mcp.server
```

The server communicates via stdio, so you'll see initialization messages but no prompt. Press `Ctrl+C` to stop.

---

## Environment variables

All products are optional. Configure the ones you need.

### Jamf Pro (optional)

| Variable                 | Description                                                   |
| ------------------------ | ------------------------------------------------------------- |
| `JAMF_PRO_URL`           | Your Jamf Pro URL (e.g., `https://yourcompany.jamfcloud.com`) |
| `JAMF_PRO_CLIENT_ID`     | OAuth API client ID                                           |
| `JAMF_PRO_CLIENT_SECRET` | OAuth API client secret                                       |

### Jamf Protect (optional)

Required for Protect tools (`jamf_protect_*`):

| Variable                 | Description                                                                  |
| ------------------------ | ---------------------------------------------------------------------------- |
| `JAMF_PROTECT_URL`       | Jamf Protect tenant base URL, without `/graphql` (e.g., `https://yourorg.protect.jamfcloud.com`) |
| `JAMF_PROTECT_CLIENT_ID` | Jamf Protect API client ID                                                   |
| `JAMF_PROTECT_PASSWORD`  | Jamf Protect API client password                                             |

### Jamf Security Cloud (optional)

Required for RISK API tools (`jamf_get_risk_devices`, `jamf_override_device_risk`):

| Variable                   | Description                                            |
| -------------------------- | ------------------------------------------------------ |
| `JAMF_SECURITY_URL`        | Security Cloud RISK API base URL (e.g., `https://api.wandera.com`) |
| `JAMF_SECURITY_APP_ID`     | Security Cloud API username                            |
| `JAMF_SECURITY_APP_SECRET` | Security Cloud API password                            |

---

## Tool filtering (optional)

Use `JAMF_TOOL_FILTER` or `--tool-filter` to select tool categories. These filters
select API primitives or workflows; either category can contain writes. Use
`--read-only` to exclude writes. Remote authorization still applies.

| Value     | Description                                                                                                    |
| --------- | -------------------------------------------------------------------------------------------------------------- |
| `all`     | (Default) Registers **all** available tools.                                                                   |
| `api`     | Registers direct API tools and documentation lookup.  |
| `complex` | Registers workflows that combine API calls. |

### Configuration examples

#### Using an environment variable

Add to your client configuration's `env` section:

```json
"env": {
  "JAMF_PRO_URL": "...",
  "JAMF_TOOL_FILTER": "api"
}
```

#### Using a command line argument

Update your client configuration's `args`:

```json
"args": ["run", "--directory", "/path/to/jamf-mcp", "jamf-mcp", "--tool-filter=complex"]
```

---

## Product filtering (optional)

You can limit which tools are registered based on the product they belong to using the `--products` command-line argument or `JAMF_PRODUCTS` environment variable. This is useful if you only want to expose tools for specific products (e.g., only Jamf Pro tools).

Available products:

- `jamf_docs` (alias: `docs`): Public API documentation lookup; no tenant credentials.
- `jamf_pro` (alias: `pro`): Jamf Pro device management tools.
- `jamf_platform` (alias: `platform`): Read-only Blueprints, compliance and DDM reports.
- `jamf_protect` (alias: `protect`): Jamf Protect endpoint security tools.
- `jamf_security_cloud` (alias: `security`, `risk`): Jamf Security Cloud risk tools.

Setup tools (`jamf_get_setup_status`, `jamf_configure_help`) are always registered regardless of filters.

### Usage examples

#### Using a command line argument

Pass a space-separated list of products:

```bash
# Only Jamf Pro tools
uv run jamf-mcp --products pro

# Pro, Protect and documentation tools
uv run jamf-mcp --products pro protect docs
```

In your client configuration:

```json
"args": ["run", "--directory", "/path/to/jamf-mcp", "jamf-mcp", "--products", "pro", "protect"]
```

#### Using an environment variable

Set a comma-separated list of products:

```bash
export JAMF_PRODUCTS="pro,protect"
```

---

## Set up API credentials

### Jamf Pro

1. Log in to Jamf Pro
2. Navigate to **Settings > System > API Roles and Clients**
3. **Create an API Role** with the permissions you need:

   | Privilege                                 | Used By                                    |
   | ----------------------------------------- | ------------------------------------------ |
   | Read Computers                            | Computer inventory lookup                  |
   | Update Computers                          | Computer inventory updates                 |
   | Read Mobile Devices                       | Mobile device inventory lookup             |
   | Update Mobile Devices                     | Mobile device inventory updates            |
   | Read User                                 | User lookup                                |
   | Update User                               | User updates                               |
   | Read Smart Computer Groups                | Computer smart group lookup                |
   | Create Smart Computer Groups              | Computer smart group creation              |
   | Read Static Computer Groups               | Computer static group lookup               |
   | Create Static Computer Groups             | Computer static group creation             |
   | Read Smart Mobile Device Groups           | Mobile smart group lookup                  |
   | Create Smart Mobile Device Groups         | Mobile smart group creation                |
   | Read Static Mobile Device Groups          | Mobile static group lookup                 |
   | Create Static Mobile Device Groups        | Mobile static group creation               |
   | Read Policies                             | Policy lookup                              |
   | Read macOS Configuration Profiles         | macOS profile lookup                       |
   | Read iOS Configuration Profiles           | iOS/iPadOS profile lookup                  |
   | Read Scripts                              | Script lookup                              |
   | Read Computer Extension Attributes        | Computer extension attribute lookup        |
   | Create Computer Extension Attributes      | Computer extension attribute creation      |
   | Read Mobile Device Extension Attributes   | Mobile device extension attribute lookup   |
   | Create Mobile Device Extension Attributes | Mobile device extension attribute creation |
   | Read User Extension Attributes            | User extension attribute lookup            |
   | Create User Extension Attributes          | User extension attribute creation          |
   | Read Categories                           | Category lookup                            |
   | Create Categories                         | Category creation                          |
   | Read Buildings                            | Building lookup                            |
   | Read Departments                          | Department lookup                          |
   | Read Computer PreStage Enrollments        | Computer PreStage lookup                   |
   | Read Mobile Device PreStage Enrollments   | Mobile device PreStage lookup              |
   | Read Mac Applications                     | Mac app lookup                             |
   | Create Mac Applications                   | Mac app creation                           |
   | Read Mobile Device Applications           | Mobile app lookup                          |
   | Read eBooks                               | eBook lookup                               |
   | Read Restricted Software                  | Restricted software lookup                 |
   | Read Patch Policies                       | Patch policy lookup                        |
   | Read API Roles                            | API role lookup                            |
   | Create API Roles                          | API role creation                          |
   | Read API Integrations                     | API integration lookup                     |
   | Create API Integrations                   | API integration creation                   |
   | Read Printers                             | Printer lookup                             |
   | Create Printers                           | Printer creation                           |
   | Update Printers                           | Printer updates                            |

   > **Tip:** The Jamf Pro interface does not allow bulk permissions import. To add permissions through the interface quicker, type in the record/item you're looking for (without the Read/Create/Update) and it will filter the available options by that item to select. For example, instead of typing in "Read User Extension Attributes" just type in "User Extension" and both Read and Update will appear for quicker adding to the list.

4. **Create an API Integration**:
   - Click **New** under API Integrations
   - Give it a name (e.g., "Jamf MCP")
   - Assign the API Role you created
   - Enable the integration
5. **Generate credentials**:
   - Copy the **Client ID**
   - Click **Generate Client Secret** and copy the secret

   > **Important:** The client secret is only shown once. Store it securely.

6. Set the environment variables:
   ```
   JAMF_PRO_URL=https://yourcompany.jamfcloud.com
   JAMF_PRO_CLIENT_ID=<your-client-id>
   JAMF_PRO_CLIENT_SECRET=<your-client-secret>
   ```

### Jamf Protect

Configure the tenant root, without `/graphql`: the server appends `/token` for
[authorization](https://learn.jamf.com/r/en-US/jamf-protect-documentation/Authorization)
and `/graphql` for [queries](https://learn.jamf.com/r/en-US/jamf-protect-documentation/Jamf_Protect_API_Endpoint).

1. Log in to your Jamf Protect tenant
2. Navigate to **Administrative > API Clients**
3. **Create an API Client**:
   - Give it a name (e.g., "Jamf MCP")
   - Note the **Client ID** and **Password**
4. Set the environment variables:
   ```
   JAMF_PROTECT_URL=https://your-tenant.protect.jamfcloud.com
   JAMF_PROTECT_CLIENT_ID=<your-client-id>
   JAMF_PROTECT_PASSWORD=<your-password>
   ```

### Jamf Security Cloud

The [RISK API](https://developer.jamf.com/jamf-security/docs/risk-api-2) uses
`https://api.wandera.com`; `radar.wandera.com` is the console rather than the API.

1. Get RISK API credentials from your Jamf Security Cloud administrator
2. Set the environment variables:
   ```
   JAMF_SECURITY_URL=https://api.wandera.com
   JAMF_SECURITY_APP_ID=<your-app-id>
   JAMF_SECURITY_APP_SECRET=<your-app-secret>
   ```

---

## Client configuration

### Local stdio

Configure a local MCP client to launch the server with these values:

| Setting | Value |
| --- | --- |
| Name | `jamf-mcp` |
| Command | `uv` |
| Arguments | `run --env-file .env --directory /path/to/jamf-mcp jamf-mcp` |
| Working directory | `/path/to/jamf-mcp` |

Use your client's supported configuration format. For clients accepting the
`mcpServers` JSON format, the equivalent configuration is:

```json
{
  "mcpServers": {
    "jamf-mcp": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/jamf-mcp", "--env-file", ".env", "jamf-mcp"]
    }
  }
}
```

The `.env` file can be supplied by the existing 1Password mount. Avoid copying
credentials into a checked-in client configuration. If your client does not
inherit the shell's PATH, use the absolute path to `uv`.

The default catalogue includes all products and documentation. Add
`--products pro platform docs` to limit it, or `--read-only` to exclude writes.
The old `jamf-mcp` command is retained as a compatibility alias.

### Remote HTTP

For the local Compose service, configure a client supporting Streamable HTTP:

| Setting | Value |
| --- | --- |
| Name | `jamf-mcp` |
| URL | `https://localhost:8443/mcp` |
| Transport | Streamable HTTP |
| Authentication | Bearer token from `.env.local` |
| TLS trust | Explicitly trust `.docker-local/server.crt` in the client |

The token is local to your machine and is separate from the Jamf credentials.
Do not disable certificate verification. Follow [Local Docker](LOCAL_DOCKER.md)
for startup and read-only live tests. Public OAuth or gateway deployments use
[Remote validation](REMOTE_VALIDATION.md).

---

## Troubleshooting

| Error                   | Cause                    | Solution                                                 |
| ----------------------- | ------------------------ | -------------------------------------------------------- |
| `401 Unauthorized`      | Invalid credentials      | Verify `JAMF_PRO_CLIENT_ID` and `JAMF_PRO_CLIENT_SECRET` |
| `403 Forbidden`         | Insufficient permissions | Add required permissions to API role in Jamf Pro         |
| `404 Not Found`         | Wrong URL                | Verify `JAMF_PRO_URL` is correct                         |
| Connection timeout      | Network issue            | Check firewall rules, verify server accessibility        |
| `JAMF_PRO_URL required` | Missing env var          | Set the environment variables                     |
| Protect tools fail      | Missing config           | Set `JAMF_PROTECT_*` environment variables               |
| Risk tools fail         | Missing config           | Set `JAMF_SECURITY_*` environment variables              |

### Find your Python path

```bash
# macOS/Linux
which python3

# Windows (PowerShell)
Get-Command python | Select-Object Source
```

### Verify installation

```bash
# Check if package is installed
python3 -c "import jamf_mcp; print(jamf_mcp.__version__)"

# Test MCP server starts
uv run jamf-mcp --help
```

## Jamf Platform (optional)

The seven Platform tools for Blueprints, compliance benchmarks and declaration
reporting require a separate Jamf Account **Platform environment** integration.
Grant `blueprints:read`,
`compliance-benchmarks:read`, and optionally `declarations:read`. Configure
`JAMF_PLATFORM_URL`, `JAMF_PLATFORM_ENVIRONMENT_ID`, `JAMF_PLATFORM_CLIENT_ID`
and `JAMF_PLATFORM_CLIENT_SECRET`. See [Platform setup](PLATFORM_SETUP.md)
for exact Jamf steps, regional URLs, 1Password variables and live probes.
Direct Pro DDM reports use the existing Pro client, as described below.

## Direct Pro reporting permissions

`jamf_get_ddm_status` uses the existing Pro client and requires both **Read
Computers** and **Read Mobile Devices**. Pass `general.managementId` from
inventory as `client_management_id`; an optional `key` reads one status item.
This calls the status report, never the DDM sync command.
[DDM API reference](https://developer.jamf.com/jamf-pro/reference/get_v1-ddm-clientmanagementid-status-items).

`jamf_get_device_compliance_information` requires **Read Device Compliance
Information**, a numeric Pro `device_id`, and `device_type="computer"` or
`"mobile"`. It reads conditional-access integration records. Its output labels
`report_type="conditional_access"` and never interprets an empty array as a
compliance verdict or CIS score.
[Computer compliance reference](https://developer.jamf.com/jamf-pro/reference/get_v1-conditional-access-device-compliance-information-computer-deviceid).

For CIS/NIST benchmark scores and rule assessments, use the separate Platform
benchmark tools and [their integration setup](PLATFORM_SETUP.md). Adding a Pro
read privilege does not turn conditional-access records into benchmark results.
