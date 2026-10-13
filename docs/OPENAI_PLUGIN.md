# Install the local Jamf plugin

The package in `plugins/jamf-mcp/` combines the Jamf MCP connection with
four skills: setup, inventory reporting, device troubleshooting and compliance
assessment. The repository marketplace makes it available for local installation
in a supported host. It launches the server over stdio with `--read-only`. The server also supports
writes, but live testing has covered reads only. Keep the packaged restriction
until you have validated any intended writes on a disposable tenant.

## Install the server command

From a reviewed checkout, run:

```bash
uv tool install --editable .
```

Put `jamf-mcp` on the MCP client's PATH. If the desktop host cannot find it,
set `command` in your local copy of `mcp.json` to the executable's absolute path.
Keep that machine-specific change out of the shared package.

The installed command uses this checkout and does not fetch code at startup.
The server starts without credentials, so setup and public documentation tools
are available immediately.

## Configure tenant access

The server inherits credentials from its process environment. Follow
[Installation](INSTALLATION.md) for product credentials and
[Platform setup](PLATFORM_SETUP.md) for benchmark and Blueprint access.
Use your existing secret injection or password manager.

For an env file, a local command override can launch `uv run` with an absolute
repository directory and env-file path. See
[Local stdio](INSTALLATION.md#local-stdio). Preserve the package's arguments,
including `--transport stdio` and `--read-only`. Keep credentials out of plugin
files, marketplace entries and archives.

The package enables Pro, Platform and documentation, with all tool categories
and read-only mode. These arguments override environment defaults. Protect and
Security Cloud are outside this package. Read-only mode removes write tools and
rejects direct calls to their names. Grant backend API roles only the reads
needed for your workflows.

## Install from the repository marketplace

`.agents/plugins/marketplace.json` points to `./plugins/jamf-mcp`, relative
to the repository root. In a supported local host:

1. Refresh or restart the app.
2. Open the plugin directory and select the **Jamf MCP** source.
3. Install **Jamf MCP** and start a new chat.
4. Select the plugin and run its setup skill.

The marketplace makes the package available. Installation and tool approval
policy are controlled by the host. Use one Jamf connection in the test chat.
If you installed the old `jamf-read-only` package, install the renamed `jamf-mcp`
package and disable the old connection to avoid duplicates.

The source labels and installation flow still need verification in the intended
host. Terminal checks prove the packaged server, not marketplace installation
or automatic skill selection.

## Check the installation

Run `uv sync --extra dev` and `./scripts/check.sh` for offline validation.
The plugin contract test launches the packaged command through MCP in modern
and legacy modes and checks read-only discovery, setup and direct-write denial.

In a new host chat, use real identifiers from your test tenant:

| Prompt or case | Expected behavior |
| --- | --- |
| What is the Jamf setup status? | Reports configured products without claiming verified tenant access |
| List ten computers with names and serial numbers | Returns a Pro inventory sample and states coverage |
| Investigate DDM status for a selected computer | Resolves identity and uses `general.managementId` for Pro DDM |
| Assess a selected CIS benchmark | Uses Platform rule/device results and states unknowns |
| Assess CIS compliance without Platform access | Reports missing access rather than substituting Pro conditional access |
| Troubleshoot a name matching several devices | Asks which device to use |
| Change a computer's asset tag | Write tool is unavailable and the change remains unexecuted |

Record host/version, package version, product, tool and outcome in
[Validation](VALIDATION.md). Keep tenant records and credentials out of reports.

## Other connection options

For a local TLS service instead of stdio, use [Docker Compose](DOCKER.md).
ChatGPT web needs a reachable connection to the MCP server. A local stdio install
does not provide that path. Optional hosted packaging and connection guidance
lives in [Remote validation](REMOTE_VALIDATION.md#optional-plugin-packaging).
