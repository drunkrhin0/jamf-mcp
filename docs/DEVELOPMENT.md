# Development

Install the development environment with `uv sync --extra dev`, then run
`./scripts/check.sh`. The same check runs in CI. `./run_tests.sh` is a compatibility
wrapper for these offline checks; its old mutating live-test mode has been retired.

Tests under `tests/` call registered production tools through MCP clients.
Isolate backend HTTP effects with mocked transports. Documentation adapter tests
also isolate the upstream MCP client. Keep protocol results and authorization
checks at the real MCP interface.

## Change tools

Implement tools in the matching `src/jamf_mcp/tools/` module with `@jamf_tool`.
Set read-only and destructive hints to describe actual state changes; the remote
scope middleware enforces authorization. Tenant tools return JSON with `success`;
documentation tools can return native `CallToolResult` objects. The shared
registry preserves both contracts.

Update [Tools](TOOLS.md), [Installation](INSTALLATION.md), and README counts when
the catalogue or privileges change. Verify endpoints and permissions with the
integrated [documentation lookup](DOCUMENTATION.md), especially when choosing
between Pro and Platform credentials. See [Architecture](ARCHITECTURE.md) for
the registration, transport and authorization boundaries.

## Live checks

Use [Local Docker](LOCAL_DOCKER.md) for tenant reads and
[Remote validation](REMOTE_VALIDATION.md) for deployed endpoint probes.
Report Pro, Platform, Protect, Security Cloud and documentation results separately.
Configured credentials alone do not prove upstream access. Do not run mutation
tests against production. Blueprint and benchmark reads need the separate
[Platform integration](PLATFORM_SETUP.md).

## Dependencies

`pyproject.toml` defines supported dependencies; `uv.lock` pins the resolved set.
`requirements.txt` is retained for pip users, and tests enforce its parity with
runtime metadata. To refresh compatible stable releases, run `uv lock --upgrade`
followed by `uv sync --frozen --extra dev` and the shared check. Rebuild Compose
and repeat live read-only checks after runtime dependency changes.

The lock supports Python 3.10 and later. Some dependencies have older resolutions
for Python 3.10; exact transitive pins, such as Pydantic's core version, can also
prevent choosing a package's independent latest release. Do not remove those
constraints merely to make an outdated-package report empty.

## Dependency and cleanup validation on 7 October 2026

The dependency lock was refreshed against the package registry. The full suite
passed on Python 3.10.22, 3.13.14 and 3.14.8: 254 tests on each runtime. Lint passed
on the local development environment. The outdated-package recheck reported only
`pydantic-core`: installed Pydantic 2.13.5 requires core 2.46.5 exactly, so the
independent core 2.49.0 release is not a compatible upgrade.

The Docker build retains uv 0.12.23, the current stable version checked against
[PyPI](https://pypi.org/project/uv/). CI now uses
[checkout 7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1) and
[setup-uv 10.1.0](https://github.com/astral-sh/setup-uv/releases/tag/v10.1.0).
Hosted CI execution remains to be verified after pushing these changes.

Claude-specific instructions were replaced by repository skills under
`.agents/skills`. The unused model module, duplicate live runners, name-mapping
checker and remediation generator were removed. `run_tests.sh` remains only as
an offline compatibility wrapper. Historical migration documents moved to
`docs/archive/`, which is ignored by Git. Current instructions live in Development
and Architecture.

The subsequent source cleanup removed twelve unused `JamfClient` methods and
three duplicate raising client getters. Tools use the safe getters, which return
the standard onboarding error when a product is unavailable. These removed
Python helpers are no longer part of the package API; the MCP tool catalogue,
`jamf_mcp` import name and `jamf-mcp` command remain compatible.

The four existing prompt names now provide task guidance tied to available tools.
Documentation tool descriptions use the upstream specification titles and paths.
The README links the MIT license; upstream copyright notices remain in source.

The final Docker runtime uses Python 3.13.16 and excludes build tools and caches.
The full suite and lint passed on that patch release. The dependency recheck
still reports only the Pydantic-constrained core version. See the
[latest dependency scan record](LOCAL_DOCKER.md#final-dependency-scan-and-project-rename-on-7-october-2026)
for remaining image advisories; current dependency versions do not imply a clean
operating-system vulnerability scan.


Container-specific security tests in `tests/test_container_security.py` run with
`JAMF_MCP_CONTAINER_SECURITY=1` in the patched Linux image. They are skipped on
host interpreters. The Alpine verification passed 260 tests and 68 subtests;
the deployed runtime passed the same six security cases. See
[container patch maintenance](../docker/SECURITY_PATCHES.md) before changing its
base or removing backports.
