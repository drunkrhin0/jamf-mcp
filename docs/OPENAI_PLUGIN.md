# Jamf plugin for ChatGPT and Codex

The portable package in `plugins/jamf-read-only/` bundles setup checks,
inventory reporting, device troubleshooting and compliance assessment skills
with the Jamf MCP connection. ChatGPT and Codex share a universal public plugin
directory; one published package can serve both. Local/repository marketplaces
are separate distribution sources whose availability varies by surface. See
[OpenAI plugin architecture](https://developers.openai.com/plugins/concepts/plugins)
and [packaging](https://developers.openai.com/plugins/build/plugins).

The source package uses local stdio. The helper below packages the same identity
and skills with a remote connection instead. It does not deploy the server,
register a ChatGPT connection or publish/install the plugin. A local installation
does not make the Mac's localhost endpoint reachable by ChatGPT web.

## ChatGPT connection and shared package

For private testing, connect the MCP server through either a reachable HTTPS
endpoint or Secure MCP Tunnel. The tunnel can reach a private stdio or HTTP
server without exposing it publicly. Public directory submission requires a
public HTTPS endpoint. Follow the official
[connection and testing guide](https://developers.openai.com/plugins/deploy/connect-chatgpt).

1. Choose a hosted endpoint or set up Secure MCP Tunnel for the local service.
   Keep the server in `--read-only` mode with Pro, Platform and documentation
   enabled. Backend credentials stay on that server, using the existing secret
   injection. The tunnel's authentication and workspace setup require their own
   validation; the current localhost bearer check does not establish them.
2. In ChatGPT Plugins, select **Add custom MCP server**, enter the actual HTTPS
   URL including `/mcp`, or choose **Tunnel** and its actual tunnel ID. Configure
   authentication and select **Create as a plugin**. Copy the registered
   `plugin_asdk_app...` ID from the resulting connection's browser URL.
3. Package the shared skills with that registered connection. Supply the exact
   ID; the shell variable below must already contain it:

   ```bash
   uv run python scripts/package_openai_plugin.py --app-id "$JAMF_CHATGPT_APP_ID" --output dist/jamf-read-only
   ```

   This creates `plugin.json`, `.app.json` and all four skills. It omits the
   local stdio entry so the host uses the registered connection. Add the result
   to a supported local marketplace for testing, or use it for publication once
   release requirements are met. The repository marketplace continues to point
   to the local stdio package.
4. Install/enable the package in the intended host, start a new chat, select
   **Jamf Read-only**, and run setup. Test **Check Jamf setup status through this
   plugin**, then **Read one computer to verify Jamf Pro access**. Repeat in
   ChatGPT and Codex and record each outcome separately. Skill invocation and
   terminal probes alone do not prove the installed connection works.

For a portable package that connects directly to a hosted HTTPS server, supply
its actual URL instead of a registered app ID:

```bash
uv run python scripts/package_openai_plugin.py --url "$JAMF_MCP_RESOURCE_URL" --output dist/jamf-read-only-http
```

The helper emits a `streamable-http` `mcp.json` and copies only the shared
manifest and skills. It requires a new output directory, includes no tokens,
headers or environment files, and does not invent a URL or app ID. Authentication
is configured through the connection/server. Remote read-only enforcement must
be configured on the server; package metadata alone does not enforce it.

No hosted URL, tunnel ID or registered ChatGPT connection is available as of
9 October 2026. Package preparation is available; live ChatGPT acceptance remains
pending that connection. The local server evidence below remains separate.

## Local setup

From a reviewed checkout of this repository, install the server executable:

```bash
uv tool install --editable .
```

Ensure `jamf-mcp` is on the MCP client's PATH. The plugin calls that installed
executable, so it does not depend on the client's working directory or fetch
code at startup. If the desktop host cannot locate it, set `command` in your
local copy of `mcp.json` to the executable's absolute path. Keep that
machine-specific change out of the shared package.

The server inherits credentials from its process environment. Configure Pro and
Platform through [Installation](INSTALLATION.md) and
[Platform setup](PLATFORM_SETUP.md), using your existing secret injection.
For a local env file, a local-only command override can launch `uv run` with an
absolute repository directory and absolute env-file path as described in
[local stdio configuration](INSTALLATION.md#local-stdio). Preserve all server
arguments from the package, including `--read-only` and `--transport stdio`.
Do not put credentials in the plugin, marketplace, chat or archive.
The package starts without credentials; setup and public documentation reads
are available while tenant tools report missing configuration.

The repository marketplace at `.agents/plugins/marketplace.json` points to
`./plugins/jamf-read-only`, relative to the repository root. In a supported
local host, refresh/restart the app, select the Jamf MCP Development source in
the plugin directory, install Jamf Read-only and start a new chat. Discovery
and these labels need confirmation in the actual host. The marketplace makes
the plugin available; it does not automatically enable it or change tool
approval policy. Avoid enabling a second Jamf connection in the same test chat.

The launch arguments explicitly choose stdio, read-only mode, all tool
categories and the Pro, Platform and documentation products. These override
transport/product/filter environment defaults. Protect and Security Cloud are
outside this initial package. Read-only mode removes write tools and rejects
direct calls to their names; skills provide workflow guidance, while the server
provides the execution boundary. Backend API roles should also grant only the
reads needed for the chosen workflow.

## Acceptance checks

Run `uv sync --extra dev` and `./scripts/check.sh`. The plugin contract test
launches the installed command with the package's arguments through the real
MCP stdio client. It checks discovery, structured setup results and rejection
of a direct write call without tenant credentials or upstream requests.

In a new host chat, try these cases with your intended test tenant:

| Prompt or case | Expected evidence |
| --- | --- |
| What is the Jamf setup status? | Structured configuration result; no claim of tenant access |
| List ten computers with names and serial numbers | Successful Pro inventory read, with coverage stated |
| Investigate DDM status for computer ID 42 | Device identity resolved; general.managementId used for Pro DDM |
| Assess the selected CIS benchmark and show failed rules | Platform benchmark identity, rule counts and explicit unknowns |
| Assess CIS compliance without Platform access | Missing Platform access reported; Pro conditional access is not substituted |
| Troubleshoot a device name matching several records | Clarification before selecting a target |
| Set computer 42's asset tag | Change remains unexecuted; write tool absent |

Use real identifiers from the test tenant instead of example ID 42. Record the
host/version, package version, tool, product, coverage and outcome. Validate
Pro, Platform benchmarks, DDM and documentation separately. Setup status and
offline tests do not prove live access or reliable skill selection.

## Offline validation on 9 October 2026

`uv sync --extra dev` completed. The shared check passed 256 tests with six
container-only tests skipped, and lint passed. Both portable manifests passed
their published Agent Plugins 1.0.0 JSON schemas; all three skills passed the
Skill Creator validator. Validation helpers used temporary dependencies;
project runtime requirements and the lockfile are unchanged.

The launch contract passed for modern and legacy MCP clients. These offline
results do not establish desktop installation, skill selection or tenant access.
The subsequent live run is recorded below.

## Live stdio validation on 9 October 2026

The packaged `jamf-mcp` command and exact `mcp.json` arguments were launched
through the MCP SDK client from this Codex chat's terminal. The repository
virtual environment was added to the test process PATH, and `uv run --env-file
.env` supplied the existing 1Password credential mount. The command was not
available on the ordinary shell PATH before that override. Desktop installation
still requires the executable setup above or a local absolute command path.

| Check | Result |
| --- | --- |
| MCP discovery | Passed; 46 tools, all marked read-only |
| Structured setup status | Passed |
| Pro inventory | Passed; ten rows sampled from 101 reported computers, all ten with names and serials |
| Pro device detail | Passed for one sampled computer; management ID available |
| Pro DDM status | Passed using that computer's returned management ID |
| Pro conditional access | Passed; empty records, explicitly not a compliance verdict |
| Platform benchmarks | Unconfigured; live benchmark access remains unverified |
| Public documentation | Specification discovery and inventory endpoint search passed |
| Direct write request | Rejected by the read-only server |

This run used real tenant and documentation requests, with no tenant mutations.
Only aggregate outcomes were printed and stored locally in the ignored
`.docker-local/plugin-e2e-2026-10-09.json`; credentials and tenant records were
not copied into the report. Protect and Security Cloud were not tested.

The current chat exposed no Jamf tools and the plugin directory search did not
return this private package. Thus this validates the packaged server through
MCP, not desktop marketplace installation or automatic skill selection. Those
host checks require installing the local plugin and starting a fresh chat.
Hosted OAuth also remains untested.

## Public release status

A public-directory release needs the hosted HTTPS connection described above,
OAuth configuration and live account-linking checks. Follow
[Remote validation](REMOTE_VALIDATION.md) for scope denial, expiry/refresh and
per-product evidence. Use one server instance per Jamf credential set; current
callers share that instance's backend tenant. Publish the same package once for
the shared ChatGPT/Codex directory after both host acceptance runs pass.

Public submission also needs directory metadata, privacy/terms information,
a sample tenant, five positive and three negative review cases and a walkthrough;
see [submission requirements](https://developers.openai.com/plugins/deploy/submission).
No public connection, publication or live host acceptance is claimed by this
change. Review the package in a draft PR before release.

## Shared package update on 9 October 2026

Version 0.2.0 adds the setup-status onboarding skill and a helper that prepares
the same workflows for a hosted MCP URL or registered ChatGPT connection.
The shared check passed 266 tests with six container-only skips and lint passed.
Packaging checks cover both connection formats, skill preservation, invalid
connection metadata and refusal to overwrite existing output. The local stdio
contract still passes for modern and legacy clients. These are offline checks;
ChatGPT registration, installation and live reads remain pending.
