# Development

Install dependencies with `uv sync --extra dev`, then run `./scripts/check.sh`.
CI runs the same check. `./run_tests.sh` is an offline compatibility wrapper.

Tests call registered production tools through MCP clients. Mock backend HTTP
transports and the documentation service to keep these checks offline. Verify
protocol results and authorization at the real MCP interface.

## Change tools

Add tools to the matching `src/jamf_mcp/tools/` module with `@jamf_tool`.
Set safety annotations to match their behavior. Remote scope enforcement uses
these annotations. Tenant tools return JSON with `success`; documentation tools
can return native `CallToolResult` objects. The registry preserves both contracts.

Update [Tools](TOOLS.md), [Installation](INSTALLATION.md), and README counts when
the catalogue or privileges change. Verify Jamf endpoints and permissions with
[Documentation lookup](DOCUMENTATION.md), particularly when choosing between Pro
and Platform credentials. [Architecture](ARCHITECTURE.md) covers registration,
result contracts and authorization boundaries.

## Validate changes

Use [Docker setup](DOCKER.md) for live read-only checks. Record Pro,
Platform, Protect, Security Cloud and documentation results separately in
[Validation](VALIDATION.md). Configuration status alone does not prove upstream
access. Run mutation tests only against an agreed disposable tenant.

Platform reads need the [separate integration](PLATFORM_SETUP.md).
[Remote validation](REMOTE_VALIDATION.md) is optional guidance for hosted OAuth
or gateway deployments.

## Dependencies and container patches

`pyproject.toml` defines supported dependencies; `uv.lock` pins the resolved set.
Tests check runtime dependency parity with `requirements.txt` for pip users.
To refresh compatible releases, run:

```bash
uv lock --upgrade
uv sync --frozen --extra dev
./scripts/check.sh
```

Rebuild Compose and repeat live reads after runtime dependency changes. The lock
supports Python 3.10 and later, including alternate resolutions for older Python
versions. Keep exact transitive constraints when their parent package requires
them, even if an independent newer release exists.

Read [Container security patches](../docker/SECURITY_PATCHES.md) before changing
the image base or removing backports. The six container security regressions run
with `JAMF_MCP_CONTAINER_SECURITY=1` in the patched Linux image and are skipped on
host interpreters. That guide contains the runtime verification and scan commands.

## Local plugin

The plugin lives in `plugins/jamf-mcp/`; the repository marketplace is
`.agents/plugins/marketplace.json`. Follow [Plugin setup](OPENAI_PLUGIN.md) for
installation and host checks. The shared check launches the packaged command
through MCP and verifies its read-only catalogue and direct-write rejection.

Keep credentials and machine-specific paths out of shared package files.
`scripts/package_openai_plugin.py` can prepare an optional remote package using
an actual hosted endpoint or registered connection. Generated files belong in
ignored `dist/`. See [Remote packaging](REMOTE_VALIDATION.md#optional-plugin-packaging).

## Semantic releases

Use Conventional Commits: `fix:` for a patch, `feat:` for a minor, and `feat!:`
or a `BREAKING CHANGE:` footer for a major. Docs-only and ordinary chores do not
start a release. The Python package, runtime, lock entry and plugin share one
version, currently bootstrapped at 0.3.0.

On `main`, [Release Please](https://github.com/googleapis/release-please-action)
updates a release PR with version changes and a generated changelog. Merge that
PR when ready to release. CI creates a draft with a `vX.Y.Z` tag, tests that exact
revision on Python 3.10 and 3.14, scans history, and builds a wheel, source archive
and local-plugin ZIP. It publishes the draft only after those checks pass.

The workflow uses `GITHUB_TOKEN` and requires Actions to be allowed to create
pull requests. GitHub combines this with approval permission in its "Allow
GitHub Actions to create and approve pull requests" setting. It is enabled for
this repository with the owner's approval; default workflow permissions remain
read-only.
Bot-created PRs do not trigger the ordinary PR workflows with
this token; the release workflow independently validates the tagged revision.
To retry a failed draft, rerun the **Semantic release** workflow on `main` with
its existing tag in `draft_tag`. The workflow does not upload to PyPI or a plugin
directory. Hosted release execution remains unverified until this setup reaches
`main` and a release PR is merged.
