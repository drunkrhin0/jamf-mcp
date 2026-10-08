# Jamf Platform read-only setup

Blueprints and Compliance Benchmarks use Jamf Account's Platform API.
Keep the existing Jamf Pro API role/client for inventory and policies, and
create this separate integration for the seven Platform reporting tools.

## Create the integration in Jamf

1. Sign in to **Jamf Account** with an Administrator account, or a custom role
   with access to **Integrations**.
2. Open **Integrations** and create an integration named `Jamf MCP read-only`.
3. Choose the **Platform environment** scope and select the environment
   containing your Jamf Pro tenant. Permissions shown depend on the products
   available in that environment.
4. Grant the read permissions below. Save the integration.
5. Copy its **environment UUID**, **client ID** and **client secret** directly
   into the existing `Jamf MCP read-only` 1Password Developer Environment.
6. Confirm the environment's hosting region. Use its regional gateway URL.

| Capability | Integration permission |
| --- | --- |
| Blueprint list and definitions | `blueprints:read` |
| Benchmark configuration, rule statistics, device results and overall percentage | `compliance-benchmarks:read` |
| Optional declaration status and device channels | `declarations:read` |

These tools need no create, update, delete, deploy or execute permissions.
`devices:read` is not needed for the implemented tools. Platform device UUIDs
come from benchmark device results; numeric Jamf Pro inventory IDs cannot be
used for declaration reporting. A general inventory ID lookup is not included.

Jamf Pro's API role selector may also display capability names such as
`blueprints read`, `compliance-benchmarks read`, and `declaration-reporting read`.
Their presence does not configure this MCP's separate Platform gateway client.
The implemented gateway tools use Jamf Account integration credentials and an
environment UUID, as specified by the gateway reference. Do not treat permission
labels alone as proof that a direct Jamf Pro client can call those gateway APIs.

`Read Device Compliance Information` covers Pro's conditional-access device
compliance endpoints. It is distinct from Compliance Benchmark rule results.
Pro also exposes `/api/v1/ddm/{clientManagementId}/status-items` with inventory
read privileges. Those direct Pro reads do not require a Platform environment
UUID, and are exposed separately as `jamf_get_ddm_status` and
`jamf_get_device_compliance_information`. They are distinct from the seven
gateway tools. On 7 October 2026,
this tenant's `/api/schema` listed those Pro endpoints and no Blueprint or
benchmark endpoints. The schema alone does not rule out undocumented routes.

Sources: [Jamf Platform getting started](https://developer.jamf.com/platform-api/reference/getting-started-with-platform-api)
and [Platform API fundamentals](https://developer.jamf.com/platform-api/reference/platform-api-fundamentals).

## Add four variables to 1Password

Add these alongside the existing `JAMF_PRO_*` variables. The existing mount at
this repository's `.env` supplies both sets to Compose. Edit the Environment in
1Password; leave `.env.local` for the generated MCP reader token and host IDs.

| Variable | Value |
| --- | --- |
| `JAMF_PLATFORM_URL` | Exactly `https://us.api.jamfcloud.com`, `https://eu.api.jamfcloud.com`, or `https://apac.api.jamfcloud.com`, matching the environment's hosting region |
| `JAMF_PLATFORM_ENVIRONMENT_ID` | The selected Platform environment UUID |
| `JAMF_PLATFORM_CLIENT_ID` | The new Jamf Account integration client ID |
| `JAMF_PLATFORM_CLIENT_SECRET` | The new integration client secret; conceal this value |

The URL is a regional gateway base URL. Do not append `/api`, `/auth/token`,
`/tenant/...` or `/mcp`. Your `company.jamfcloud.com` URL stays in
`JAMF_PRO_URL`. The server obtains tokens from the selected gateway and sends
`X-Environment-Id` on reporting requests. Gateway tokens are region-specific.
Jamf documents 15-minute access tokens and six-month integration credential
expiry; plan to rotate the integration credentials before they expire.
[Authentication reference](https://developer.jamf.com/platform-api/reference/getting-started-with-platform-api).

## Recreate and run live reads

Approve the 1Password mount, then recreate the service to pick up new values:

```bash
docker compose --env-file .env.local up -d --build --force-recreate --wait
```

The service exposes Pro and Platform tools, excludes write tools, and accepts
only the local reader identity. First probe the MCP connection, then separately
probe each Platform permission:

```bash
docker compose --env-file .env.local exec -e SSL_CERT_FILE=/run/tls/server.crt jamf-mcp python scripts/validate_remote.py

docker compose --env-file .env.local exec -e SSL_CERT_FILE=/run/tls/server.crt jamf-mcp python scripts/validate_remote.py --backend jamf_platform

docker compose --env-file .env.local exec -e SSL_CERT_FILE=/run/tls/server.crt jamf-mcp python scripts/validate_remote.py --backend jamf_platform_compliance
```

The probes print pass/fail without response bodies or credentials. A successful
Blueprint probe does not validate compliance or DDM authorization. DDM needs an
actual Platform device UUID or declaration identifier and a nonempty filter;
validate it with an authorized read of an existing resource.

Configuration status confirms credentials are present, not that Jamf accepts
them. A 401 indicates an authentication failure. For a 403, check the integration
permission, environment scope, hosting region and product availability.
The server retains certificate verification and does not follow API redirects.

## Example requests

- “List the Blueprints.”
- “Show the definition of Blueprint `<blueprint UUID>`.”
- “List the compliance benchmarks, then show the overall percentage for `<benchmark ID>`.”
- “Show rule statistics for `<benchmark ID>`, then list FAILED devices for `<rule ID>`.”
- “Show declarations on Platform device `<device UUID>` with filter `active==true`.”

Benchmark definitions describe configured rules. Rule and device reports show
actual assessments. Device results are per rule; the API exposed here does not
provide a single per-device report covering every rule.
Declaration filters exclude pending declarations, so empty results do not prove
that every assigned Blueprint has arrived. See the [tool reference](TOOLS.md#jamf-platform)
and [verified API contracts](PLATFORM_API_RESEARCH.md) for paths and limits.

## Validation status

Offline tests exercise the production MCP tools with simulated Jamf HTTP
responses, including authentication, environment context, reporting results and
read-only authorization. Live Jamf Pro reads were previously verified locally.
Live Platform authentication and reporting remain pending until the separate
integration credentials are supplied and its probes pass.

### Direct Pro reads checked on 7 October 2026

Using the existing Pro client and one computer selected internally, the direct
conditional-access device compliance endpoint returned HTTP 200 with an empty
record array. This confirms access for that sampled device, not benchmark
results or a compliant device state. The DDM status-items endpoint returned
HTTP 403 with `INVALID_PRIVILEGE`. This tenant’s schema and the
[DDM API reference](https://developer.jamf.com/jamf-pro/reference/get_v1-ddm-clientmanagementid-status-items)
require both **Read Computers** and **Read Mobile Devices**. The supplied role
list includes Read Computers but omits Read Mobile Devices; add that read
privilege before retrying DDM. These checks called Pro directly and did not
exercise the seven Platform MCP tools.

After Read Mobile Devices was added to the same Pro role, a fresh-token retry
returned HTTP 200 with DDM status items for the sampled computer. This verifies
the direct Pro DDM read. It does not validate Blueprint definitions, benchmark
results, the Platform gateway, or fleet-wide declaration deployment success.

After exposing these reads as MCP tools, the rebuilt local service returned
DDM status items for two sampled computers through
`jamf_get_ddm_status`, without truncation. Both calls to
`jamf_get_device_compliance_information` returned empty conditional-access
records and an explicit note that they establish no CIS verdict. The MCP
catalogue contained 37 read-only tools. A benchmark call stopped at the local
"Jamf Platform is not configured" check; upstream CIS access remains untested.

## Read CIS results for a named Mac

The current benchmark OpenAPI files, fetched directly on 7 October 2026,
confirm `compliance-benchmarks:read`, regional GA gateway paths, and
`X-Environment-Id`. Some cached HTML pages still show beta hosts, tenant URL
segments and old privilege names; do not substitute those into current requests.

With a configured Platform integration:

1. Call `jamf_platform_get_benchmarks()` and choose the actual CIS benchmark ID.
2. Call `jamf_platform_get_benchmark_rules(benchmark_id=...)` and page through
   `results` using `totalCount`. The results include per-rule assessments.
3. For each relevant rule, call `jamf_platform_get_benchmark_devices` with the
   benchmark ID, returned `rule_id`, and `search="Example Mac"`, replacing the
   example with the intended device name. Search matches device name/ID; confirm the
   returned device identity and page through matches. Omit `rule_result` to
   include PASSED, FAILED and UNKNOWN results. Filtering only FAILED cannot
   establish that every rule passed when the response is empty.
4. Use `jamf_platform_get_benchmark_compliance` only for the aggregate benchmark
   percentage. It is not a per-device CIS score.

Sources: [Benchmark list](https://developer.jamf.com/platform-api/reference/gettenantbenchmarks),
[rule results](https://developer.jamf.com/platform-api/reference/v1getbenchmarkrulesstats),
[device results](https://developer.jamf.com/platform-api/reference/v1getdevicesforbenchmarkrule).

The conditional-access Pro endpoint is associated with device compliance
integration such as Microsoft Entra. It is not the CIS reporting source.
[Jamf inventory documentation](https://learn.jamf.com/r/en-US/jamf-pro-documentation-11.13.0/Local_User_Accounts_Category).
