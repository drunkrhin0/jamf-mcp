# Jamf Platform read-only API research

Verified against Jamf's official API reference and its embedded OpenAPI specifications on 7 October 2026. This records the API contract; it does not claim a live test against this organization's Platform integration.

## Connection and permissions

Create an integration in **Jamf Account → Integrations**, scoped to **Platform environment**, and select the environment containing the relevant Jamf Pro tenant. Access to Integrations requires an Administrator or custom role with Integrations privileges. Copy the environment UUID from the integration details. Permissions available depend on the products in that environment. See [Getting started](https://developer.jamf.com/platform-api/reference/getting-started-with-platform-api).

Use `https://{region}.api.jamfcloud.com`, where region is `us`, `eu`, or `apac`, matching the product hosting region. Request a token from `POST /auth/token` on that same host with form fields `grant_type=client_credentials`, `client_id`, and `client_secret`. Use `Content-Type: application/x-www-form-urlencoded`. API requests require `Authorization: Bearer <token>` and `X-Environment-Id: <environment UUID>`. Tokens are region-locked and expire after 900 seconds; renew using client credentials and the returned `expires_in`. Integrations have a six-month validity period. See [Platform API fundamentals](https://developer.jamf.com/platform-api/reference/platform-api-fundamentals).

The current GA paths use an environment header. Older beta examples containing `apigw.jamf.com`, `/api`, or `/tenant/{tenantId}` must not be copied into this implementation. Some embedded specification descriptions still say “Beta API Gateway”; their actual server URLs use the GA hostname. See [Getting started](https://developer.jamf.com/platform-api/reference/getting-started-with-platform-api).

Grant `blueprints:read`, `compliance-benchmarks:read`, and `declarations:read` for the operations below. These are the permissions required by the gateway on its **Jamf Account integration**. The customer also reports similarly named capabilities in the direct Jamf Pro API role selector; those labels alone do not establish that its credentials work with gateway authentication. No create, update, delete, deploy, or execute permissions are needed for these reads. Each operation's source below specifies its required permission.

## Blueprints

All paths below are relative to the regional base URL and require `X-Environment-Id`.

| Operation | Method and path | Parameters | Permission |
| --- | --- | --- | --- |
| List blueprints | `GET /blueprints/v1/blueprints` | `page` ≥ 0, default 0; `page-size` ≥ 1, default 100; `sort`, default `created:desc`; optional `search` of up to 1000 characters matching name/description | `blueprints:read` |
| Blueprint details | `GET /blueprints/v1/blueprints/{blueprintId}` | UUID blueprint ID; no query parameters | `blueprints:read` |
| Component catalog | `GET /blueprints/v1/blueprint-components` | `page` ≥ 0, default 0; `page-size` ≥ 1, default 100 | `blueprints:read` |

Sources: [List blueprints](https://developer.jamf.com/platform-api/reference/listblueprints), [Get a blueprint](https://developer.jamf.com/platform-api/reference/getblueprint), [List available blueprint components](https://developer.jamf.com/platform-api/reference/listcomponents).

Blueprint sort syntax is `field[:direction]` with optional comma-separated secondary fields. Do not add an assumed RSQL `filter` parameter: the blueprint list reference specifically documents `search`.

## Benchmark configuration and actual results

All of these operations require `compliance-benchmarks:read` and `X-Environment-Id`.

| Operation | Method and path | Query parameters |
| --- | --- | --- |
| List benchmark summaries | `GET /compliance-benchmarks/v1/benchmarks` | None documented |
| Get full benchmark configuration | `GET /compliance-benchmarks/v1/benchmarks/{id}` | None |
| Rule results across devices | `GET /compliance-benchmarks/v1/benchmarks/{id}/rules` | Optional `rule-search`; `page` ≥ 0, default 0; `page-size` ≥ 1, default 500; `sort`, default `ruleNumber,ruleTitle` |
| Device results for one rule | `GET /compliance-benchmarks/v1/benchmarks/{id}/devices` | **Required `rule-id`**; optional `device-search` matching device name/ID; optional `rule-result`; `page` ≥ 0, default 0; `page-size` ≥ 1, default 100; `sort`, default `ruleResult:desc` |
| Overall benchmark percentage | `GET /compliance-benchmarks/v1/benchmarks/{id}/compliance-percentage` | None |

Sources: [List benchmarks](https://developer.jamf.com/platform-api/reference/gettenantbenchmarks), [Benchmark configuration](https://developer.jamf.com/platform-api/reference/getbenchmark), [Rule statistics](https://developer.jamf.com/platform-api/reference/v1getbenchmarkrulesstats), [Devices for a rule](https://developer.jamf.com/platform-api/reference/v1getdevicesforbenchmarkrule), [Compliance percentage](https://developer.jamf.com/platform-api/reference/v1getbenchmarkcompliancepercentage).

Benchmark IDs are strings, not necessarily UUIDs. The list response contains a `benchmarks` array, without documented pagination. Do not substitute a generic `results` envelope or invent list pagination.

Rule statistics return `results` and `totalCount`. Each rule includes its ID/title, passed/failed/unknown device counts, pass percentage, and number of devices. Optional fields include rule number and discussion. These are actual result counts, rather than configuration alone. See [Rule statistics](https://developer.jamf.com/platform-api/reference/v1getbenchmarkrulesstats).

Rule device results return `results` and `totalCount`. Each result contains the Platform `deviceId`, `state` (`PASSED`, `FAILED`, or `UNKNOWN`), and optional device name. `rule-result` accepts those three state values. The overall percentage endpoint returns `compliancePercentage` between 0 and 100 and defines the figure as the sum of device compliance scores divided by the number of devices. Sources: [Devices for a rule](https://developer.jamf.com/platform-api/reference/v1getdevicesforbenchmarkrule), [Compliance percentage](https://developer.jamf.com/platform-api/reference/v1getbenchmarkcompliancepercentage).

## Declarative Device Management status

These operations require `declarations:read` and `X-Environment-Id`. `deviceId` is the **Platform device ID**, not the numeric Jamf Pro inventory ID.

| Operation | Method and path | Parameters |
| --- | --- | --- |
| Declarations reported by a device | `GET /ddm/report/v1/devices/{deviceId}/declarations` | **Required `filter`**; `page` ≥ 0, default 0; `size` ≥ 1, default 20; optional repeated `sort` |
| Device reporting channels | `GET /ddm/report/v1/devices/{deviceId}/channels` | No query parameters |
| Devices reporting a declaration | `GET /ddm/report/v1/declarations/{declarationIdentifier}/devices` | **Required `filter`**; `page` ≥ 0, default 0; `size` ≥ 1, default 20; optional repeated `sort` |

Sources: [Device declarations](https://developer.jamf.com/platform-api/reference/getdevicereportbyfilter), [Device channels](https://developer.jamf.com/platform-api/reference/getdevicechannels), [Declaration devices](https://developer.jamf.com/platform-api/reference/getdeclarationreportbyfilter).

Device declaration filters support `declarationIdentifier`, `active`, `validityState`, `declarationType`, `dateUpdated`, and `channel`. An official example selects Blueprint configurations with `declarationIdentifier==Blueprint_<blueprint UUID>*;declarationType==CONFIGURATION`; wildcard identifier matching is case-insensitive. Sort syntax here differs from benchmark APIs: `declarationType,asc`, with repeated `sort` query parameters for multiple criteria. See [Device declarations](https://developer.jamf.com/platform-api/reference/getdevicereportbyfilter).

Declaration device filters support `deviceId`, `channel`, `lastReportTime`, `active`, `validityState`, `declarationType`, and `dateUpdated`. An official example is `channel==SYSTEM;active==true`. Both filtered reporting operations state that filters apply to declarations already on the device and exclude `PENDING` status. See [Declaration devices](https://developer.jamf.com/platform-api/reference/getdeclarationreportbyfilter).

Reported entries include `active`, `validityState`, installation `status`, channel, declaration type, last-report/update timestamps, and optional failure reasons. Status values are `PENDING`, `SUCCESSFUL`, `AWAITING_SYNC`, `UNSUCCESSFUL`, and `UNKNOWN`; validity is `VALID`, `INVALID`, or `UNKNOWN`. Device reports and declaration reports have `results` and `totalCount`. The channels endpoint returns `deviceId` and a `channels` array. Sources: [Device declarations](https://developer.jamf.com/platform-api/reference/getdevicereportbyfilter), [Device channels](https://developer.jamf.com/platform-api/reference/getdevicechannels).

## Implementation limits and follow-up

- The documented benchmark device report is a **per-rule** drill-down. This research did not establish a separate endpoint giving every rule result for one device, or a per-device overall score. Building such a view would require combining the documented reads; it must not claim an unsupported endpoint.
- Declaration filtering deliberately omits pending declarations. Empty or successful filtered reports alone do not prove every assigned Blueprint declaration has arrived.
- Reporting reads require Platform device IDs. Benchmark device results provide these. If users want arbitrary inventory lookup or a numeric Pro-to-Platform ID mapping, verify the Devices API before adding that behavior; `devices:read` is an additional capability. See [Platform API fundamentals](https://developer.jamf.com/platform-api/reference/platform-api-fundamentals).
- API availability and authorization must still be validated using the customer's environment integration. A `403` can indicate missing permission, the wrong scope level, or an invalid version path; it is not sufficient evidence that an API role merely needs another privilege. See [Platform API fundamentals](https://developer.jamf.com/platform-api/reference/platform-api-fundamentals).

## Contract recheck

On 7 October 2026, direct downloads of the official Markdown/OpenAPI pages
for benchmark lists, rule statistics and device reports confirmed the existing
GA paths and `compliance-benchmarks:read` requirements. Cached HTML fetches
returned older beta paths, so those were not used to change the implementation.
The direct Pro conditional-access read is not a CIS benchmark result source.
