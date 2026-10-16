# Validation record

Only read-only workflows have been tested against live services. The server also
supports writes; the bundled plugin and Compose setup disable them. Configuration
status and offline tests are separate from accepted backend requests.

## Release checks on 13 October 2026

The runtime fixes were committed as `6cf7d9d`, based on `9d0dc9e`.

| Check | Result |
| --- | --- |
| `./scripts/check.sh` | 264 passed, six container-only skips, lint passed |
| Documentation and MCP contract tests | 108 passed |
| Gitleaks 8.30.1 | No findings in the release candidate or all three commits at `6cf7d9d` |
| Wheel and source distribution | Built; source excluded private environment/runtime files, wheel included the licence |
| Installed wheel outside checkout | Modern and legacy MCP modes passed with 46 read-only tools and write rejection |
| Rebuilt Docker service | TLS admission, authenticated discovery and setup passed |
| Container security regressions | All six passed as the runtime user |

Hosted contract CI passed for `9d0dc9e` on Python 3.10 and 3.14 on 9 October.
See the [run](https://github.com/drunkrhin0/jamf-mcp/actions/runs/37889552694).
Subsequent fixes have local validation; secret-scan CI now covers `codex/**`.

| Live path | Result |
| --- | --- |
| Pro inventory, details and DDM | Passed on sampled computers; no fleet-wide deployment conclusion |
| Pro conditional access | Passed; empty records establish no compliance verdict |
| Documentation | All nine tools passed representative calls; generic wrapper used `list-specs` |
| Documentation server variables | Advertised Pro/Classic titles failed directly against Jamf's upstream service |
| Platform Blueprints and benchmarks | Unconfigured; missing access reported correctly, live access unverified |
| Protect | Credentials absent; live access unverified |
| Security Cloud | Credentials absent; live access unverified |
| Write admission | Direct write call received HTTP 403 from the read-only Docker endpoint |
| Malformed documentation input | JSON `null`, array and string rejected locally with the intended error |

Live calls used existing Pro credentials. No Jamf mutations were executed, and
reports contain no tenant records or credentials. The Docker endpoint bound to
localhost. Older Pro inventory checks sampled ten of 101 reported computers.

## Plugin and skills

The renamed `jamf-mcp` plugin is version 0.3.0. Both manifests passed their
published Agent Plugins 1.0.0 schemas. All four packaged skills and both repository
skills passed structural validation. Packaged tool names and key parameters
matched the actual MCP catalogue; marketplace and onboarding paths resolved.
The 12 plugin launch/packaging cases passed, including both protocol modes.

Representative stdio reads passed for setup, one-computer inventory, details,
Pro DDM, conditional access and documentation. Platform calls reported missing
configuration. Aggregate outcomes are in the ignored local file
`.docker-local/skill-read-paths-2026-10-13.json`.

These checks verify package wiring and tools used by the skills. Marketplace
installation, automatic skill selection and full host workflows remain untested.
ChatGPT, external OAuth and gateway policy also remain unverified.

## Container evidence from 7 October 2026

The dependency audit found no known vulnerabilities in 45 locked external
package/version records. The final Alpine image scan retained two Medium Python
version matches for backported fixes; refreshed Grype data recognized zlib's
vendor fix. No advisories were hidden. Patched Alpine verification passed
260 tests and 68 subtests, including attack cases that failed before patching.

Follow [Security patches](../docker/SECURITY_PATCHES.md) for sources and repeatable
checks. Preserve raw reports and record the image ID and scanner/database versions.
These dated results do not establish a current vulnerability-free image.

## Test audit

Removed a duplicate unknown-tool test while retaining both protocol modes at
the shared catalogue owner. Strengthened malformed-input coverage to check the
intended error and zero upstream connections. The stronger test exposed the
JSON `null` bug, failed before the validation repair and passed afterward.
Independent final diff review found no actionable issues. The audit skill's
named `autoreview` workflow was unavailable; repository checks were used instead.

Older validation and audit detail remains in Git history:
`git show 6cf7d9d:docs/RELEASE_READINESS.md`.
