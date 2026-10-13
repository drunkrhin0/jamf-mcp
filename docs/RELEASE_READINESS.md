# Release readiness

Local read-only release checks passed on 13 October 2026. Local installation is
the intended release scope. Public ChatGPT/plugin acceptance remains unverified
and is outside that scope. This record covers release fixes based on commit
`9d0dc9e`. No publication, push or PR was performed during validation.

## Candidate checks

| Check | Result |
| --- | --- |
| Gitleaks 8.30.1, all Git history | Passed, two commits scanned, no findings |
| Gitleaks, candidate source files | Passed, no findings; ignored credential files excluded |
| `uv sync --extra dev` and `./scripts/check.sh` | 264 passed, six container-only skips, lint passed |
| Focused documentation and MCP contracts | 108 passed |
| Wheel and source distribution | Both built successfully |
| Installed wheel outside checkout | Modern and legacy MCP modes passed; 46 read-only tools, setup, malformed input and write rejection |
| Docker build and health | Rebuilt image passed local TLS health check |
| Container security regressions | All six passed as the runtime user |
| Independent final diff review | No actionable code or test findings |

Hosted contract CI passed for the base commit on Python 3.10 and 3.14 on
9 October. See the [run](https://github.com/drunkrhin0/jamf-mcp/actions/runs/37889552694).
The new working-tree changes have local validation only. The secret-scan workflow
now includes `codex/**` push branches, matching contract CI coverage.

## Live product and transport checks

| Product or path | Result |
| --- | --- |
| Local TLS/bearer transport | Anonymous requests denied; authenticated discovery and setup passed |
| Jamf Pro | One-computer inventory read passed through MCP |
| Documentation | All nine tools passed representative calls; generic wrapper used `list-specs` |
| Documentation server variables | Upstream failure for advertised Pro and Classic specification titles, reproduced directly against Jamf |
| Jamf Platform | Blueprint and benchmark calls reported missing configuration; live access unverified |
| Jamf Protect | Credentials absent; live access unverified |
| Jamf Security Cloud | Credentials absent; live access unverified |
| Write admission | Direct write call received HTTP 403 from read-only Docker endpoint |
| Malformed documentation input | JSON `null`, array and string rejected with the intended local error |
| ChatGPT/plugin host acceptance | Unverified; no hosted endpoint, tunnel or registered connection configured |
| External OAuth and gateway policy | Unverified; local bearer checks do not exercise these paths |

Live calls used the existing Pro credential injection. No Jamf mutations were
executed. Tenant records and credential values were not copied into this report.
Read-only mode remains enabled, and the service binds to localhost.

## Test audit

Read-only discovery covered core contracts and auth, product clients and reports,
documentation, plugin packaging, setup, dependencies, runner behavior and remote
probes. Review included production owners, callers, overlapping tests, CI and
repository history. The edit batch is limited to documentation input behavior.

### Duplicate unknown-tool test

Removed `test_unknown_docs_tool_is_protocol_error` from
`tests/test_docs_contract.py`. Its modern and legacy cases both called an unknown
local name and asserted protocol error `-32602`. They never reached documentation
code. `test_unknown_tools_are_protocol_errors` in `tests/test_mcp_contract.py`
retains the same two cases at the shared catalogue owner.

Both paths use production `register_all_tools` and its name-validation middleware.
The main server also uses this registration path. The duplicate originated in
initial release `529cb57`; history contains no distinct regression rationale.
Removal deletes nine test lines and no production seam. Risk is low, with the
focused documentation and MCP suites retaining executable proof.

### Invalid-input negative control

Strengthened `test_generic_arguments_must_be_object` in
`tests/test_docs_contract.py`. Previously it asserted only `isError`, which could
pass after an unwanted upstream connection failed. It now asserts the intended
local error and proves the upstream client was never opened. Existing forwarding
tests do not own this malformed-input contract.

The stronger test failed on the original production code for JSON `null`: title
handling produced a Python `NoneType` error before object validation. Moving the
existing validation before title handling fixes that behavior. The focused suite
then passed. Production wrappers call the shared forwarding owner, so validation
stays in a real execution path. No test-only production hook was added.
The original test dates to `529cb57`. The risk is limited to malformed generic
input, with normal forwarding, schema lookup and allowlist coverage retained.

### Retained coverage

Keep direct authorization middleware tests because HTTP denial tests can stop
requests before that inner boundary runs. Keep client error/logging tests because
protocol error formatting and secret-free logs are separate contracts. Native
documentation content preservation is an independent adapter contract. Package
launches in both protocol modes, dependency parity and container security
backports also retain distinct release or runtime risks.

The setup-help URL test remains useful for public examples, but it composes
strings rather than running actual clients. A future focused change could feed
those examples into mocked client transports. It was retained in this batch.

### Audit validation and change size

Ran `uv run --frozen pytest -q tests/test_docs_contract.py tests/test_mcp_contract.py`,
then the required `./scripts/check.sh`, distribution smoke tests and rebuilt
Docker probes. `git diff --check` passed. Production changed by two additions and
two deletions. Workflow configuration changed by one addition and one deletion.
Tests changed by twelve additions and eleven deletions, including removal of the
nine-line duplicate. Test support did not change.

The generic audit skill references OpenClaw/Vitest commands and mandatory
`autoreview`. Those scripts and skills are absent from this Python repository
and available skill directories. Repository pytest/lint checks and an independent
final diff review were used. The named `autoreview` workflow was not run.

## Optional public acceptance work

Local installation does not require directory submission or a hosted endpoint.
Before a future public ChatGPT/plugin release, configure its reachable connection and
run installation, skill selection and OAuth linking in the intended host. Follow
[Plugin setup](OPENAI_PLUGIN.md) and the official
[connection guide](https://developers.openai.com/plugins/deploy/connect-chatgpt).
Supply each remaining product's credentials through the existing secret manager
before claiming live access. Track the upstream documentation server-variables
limitation separately from the passing generic lookup path.

Rerun the checks and secret scan after forming the final release commit. This
report covers the validated release fixes, not a published tag.
