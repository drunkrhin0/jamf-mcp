# Local read-only Docker test

This Compose service runs Jamf MCP with Jamf Pro, Platform and documentation tools at `https://localhost:8443/mcp`.
Only this Mac can connect. Write tools are excluded, and the local bearer
identity has only `jamf:read`. Use a Jamf API client whose assigned API roles
grant only the reads you intend to test.

Documentation uses the same endpoint and local reader token. It needs no tenant
credentials, and makes outbound requests to `https://developer.jamf.com/mcp`
only when a documentation tool is called. No second container is required.

## Current validation status

As of 8 October 2026, the renamed Compose service receives its Pro credentials
from the 1Password mount at the current checkout's `.env` path. The Pro inventory
read, TLS admission, authenticated discovery, 46-tool read-only catalogue and
direct write denial passed. All six container security regressions passed.

All nine documentation tools passed on 7 October. Specification discovery,
endpoint details and response-schema reads passed again on 8 October, along with
rejection of upstream `execute-request`. Platform still needs its separate
credentials and live probes. Protect and Security Cloud were not included in
these live checks. External OAuth linking and gateway policy remain untested.

The latest dependency audit found no known vulnerabilities in the 45 locked
external package/version records. The image scan retains two Medium Python
version warnings for fixes backported into the runtime. See
[container patch maintenance](../docker/SECURITY_PATCHES.md) for their evidence.

## Prepare the local service

Prepare local files once:

```bash
python3 scripts/setup_local_docker.py
```

The script generates a random local token and a 30-day self-signed localhost
certificate. It preserves an existing `.env.local`. The environment file and
TLS directory are ignored by Git and excluded from the image build.

If your network uses a TLS inspection proxy, put its approved public CA
certificate bundle in `.docker-local/build-ca.pem`. Docker passes this file as
a build secret for dependency downloads. Certificate verification stays enabled,
and this extra bundle is not installed in the running image.

## Create the Jamf API role and client

Create the API role first, then the API client:

1. In Jamf Pro, go to **Settings > System > API roles and clients**.
2. Open **API Roles**, click **New**, and name the role `Jamf MCP read-only`.
   Grant **Read Computers** only and save. Leave other privileges unchecked
   for the first inventory test.
3. Open **API Clients**, click **New**, and name the client `Jamf MCP local test`.
   Assign only the `Jamf MCP read-only` role. A client's privileges combine all
   its assigned roles, so another role could grant additional access.
4. Set **Access Token Lifetime** to **300 seconds** for this test. This is a
   suggested test setting, not a required value.
5. Save, then edit the client, click **Enable API Client**, and save again.
6. Generate the client secret and store it directly in 1Password along with
   the client ID and your tenant URL.

The probe calls `GET /api/v1/computers-inventory` with a page size of one.
**Read Computers** is the required privilege for that endpoint. This role is
enough for our first live inventory test. Other MCP reads, such as policies or
groups, need their corresponding read privileges when you test them. Keep this
role limited to the reads you intend to use.

References: [Jamf API privilege requirements](https://developer.jamf.com/jamf-pro/docs/privileges-and-deprecations)
and [creating an API client](https://learn.jamf.com/r/en-US/jamf-pro-documentation-current/Creating_an_API_Client).

## Store credentials in 1Password

You can keep the Jamf credentials in a 1Password Developer Environment and
mount it at this repository's `.env` instead. Store `JAMF_PRO_URL`,
`JAMF_PRO_CLIENT_ID` and `JAMF_PRO_CLIENT_SECRET` there. Compose reads the mount
after `.env.local`, so the mounted values take precedence for the container.
Keep `.env.local` for the generated local MCP token and host UID/GID. Leave its
three Jamf values blank when using 1Password.

Add these variables directly in the `Jamf MCP read-only` Environment:

| Variable | Value | Concealed |
| --- | --- | --- |
| `JAMF_PRO_URL` | Your tenant base URL, including `https://`, such as `https://yourcompany.jamfcloud.com` | No |
| `JAMF_PRO_CLIENT_ID` | The API client's ID | Optional |
| `JAMF_PRO_CLIENT_SECRET` | The generated client secret | Yes |

For `JAMF_PRO_URL`, use the full tenant base URL: `https://company.jamfcloud.com`,
replacing `company` with your tenant name. Include `https://`. Do not add `/api`
or a login-page path. The MCP server adds the API paths itself.

1Password syncs these variables to the mounted `.env`. Edit them in 1Password,
not in the mounted file. Do not paste secrets into chat. The generated token
in `.env.local` authenticates MCP callers and is separate from the Jamf client
secret. If you are not using 1Password, fill in the three Jamf values in
`.env.local` instead.

Approve access in 1Password before running Compose. After updating credentials,
recreate the container so it receives the new values:

```bash
docker compose --env-file .env.local up -d --force-recreate --wait
```

## Start and test the service

For the first startup, build and start the service:

```bash
docker compose --env-file .env.local up -d --build --wait
```

Check TLS, unauthenticated access denial, MCP discovery, the catalogue and setup
status without contacting Jamf:

```bash
docker compose --env-file .env.local exec -e SSL_CERT_FILE=/run/tls/server.crt jamf-mcp python scripts/validate_remote.py
```

Run one live computer inventory read through MCP:

```bash
docker compose --env-file .env.local exec -e SSL_CERT_FILE=/run/tls/server.crt jamf-mcp python scripts/validate_remote.py --backend jamf_pro
```

The probe prints pass/fail status without tenant response bodies or tokens.
Setup status alone does not prove Jamf authentication. The backend command must
pass before recording a successful live Jamf read. This local test does not
validate an external client's OAuth login or gateway access policy.

### Live validation recorded on 7 October 2026

The local Compose container was recreated with credentials from the 1Password
mount. The probe passed unauthenticated access denial, authenticated MCP
discovery, tool listing, setup status, and the live `jamf_get_computer` inventory
read with `page=0` and `page_size=1`. No tenant response bodies or credentials
were printed, and no Jamf mutations were executed.

Before credentials were added, the same local deployment also passed a check
that its catalogue contained only 28 read-only tools and a direct write request
received HTTP 403. External client linking and gateway access-policy validation
remain untested.

Clients connecting directly need the generated certificate as an explicit
trusted certificate and the bearer token from `.env.local`. System certificate
trust is not changed by this setup. The container's Jamf connection uses its
normal public certificate trust. The service exposes Jamf Pro and Platform tools. Platform reads need the
separate [Jamf Account integration](PLATFORM_SETUP.md).

Stop the service with:

```bash
docker compose --env-file .env.local down
```

Live tests use the read-only endpoint probes above. The former mutating live suite has been retired.
To renew the local certificate, stop the service, remove `.docker-local/server.crt`
and `.docker-local/server.key`, rerun the setup script, and start the service.

### Platform build validation recorded on 7 October 2026

After adding the Platform tools, the rebuilt local service passed the live Pro
inventory read again. Its catalogue contained 35 read-only tools, including all
seven Platform tools, and a direct write request received HTTP 403 before
dispatch. Platform setup status showed unconfigured: live Platform reads remain
pending the separate Jamf Account integration credentials.

### Device reporting validation recorded on 7 October 2026

After adding the two direct Pro reporting tools, the rebuilt service exposed
37 tools, all marked read-only. MCP reads for two sampled computers returned
DDM status items without response
truncation. Both conditional-access reports returned empty records and the
explicit `conditional_access` report type; neither establishes a CIS verdict.
The subsequent E2E run also passed unauthenticated admission denial,
authenticated discovery, setup status, and inventory. A write-tool request with
empty arguments received HTTP 403 before tool execution. Blueprint and benchmark
MCP calls both reported that Jamf Platform is not configured, so their live
access remains unverified. No Jamf mutations were executed. These local checks
do not establish external OAuth linking or gateway access-policy behavior.

### Full inventory serial audit recorded on 7 October 2026

The computer tool supports `sections=["GENERAL", "HARDWARE"]` for inventory
list reads. This retrieves names and serial numbers without the full detail
responses that can exceed the MCP response limit. Keep page sizes small and
check for truncation before treating a fleet scan as complete.

Two complete MCP scans with `page_size=10` returned the same inventory.
Every entry had a serial number. After trimming whitespace and ignoring case,
all returned serial numbers were unique. The IDs and serials agreed across both
scans. No Jamf mutations were executed. This records the tested inventory at
that time, not a continuing guarantee of uniqueness.

### Integrated documentation E2E validation recorded on 7 October 2026

The Compose service was rebuilt and recreated with the integrated documentation
adapter. It is healthy at `https://localhost:8443/mcp` and exposes 46 read-only
tools, including all nine documentation tools. The default unfiltered catalogue
contains 68 tools.

Live requests from inside the container through the HTTPS MCP endpoint passed:

- Unauthenticated and invalid-token admission denial (HTTP 401).
- Authenticated discovery, catalogue listing and setup status.
- A one-item Jamf Pro computer inventory read.
- A direct write request denied before dispatch (HTTP 403).
- All nine documentation tools against the public upstream, including endpoint
  search, default Pro specification lookup, category endpoint details, request
  and response schemas, generic approved lookup and cache refresh.
- Rejection of the upstream `execute-request` operation.

The run exposed stale assumptions in the inherited docs adapter. The upstream
now uses qualified spec titles and `search-endpoints`; request and response
schema documentation comes from `get-endpoint`. The adapter was corrected and
redeployed, then all documentation checks passed. The offline suite and lint
also passed: 254 tests.

Platform Blueprint and benchmark calls reported unconfigured. Live Platform
access remains pending its separate credentials. Protect and Security Cloud
are excluded from this Compose catalogue and were not live-tested. No tenant
response bodies or tokens were printed, and no tenant mutations were executed.
External host OAuth linking and gateway policy were outside this local run.

### Dependency refresh validation recorded on 7 October 2026

After retiring the unused models and duplicate live-test scripts and refreshing
`uv.lock`, the Compose image was rebuilt and the service recreated. The service
remained healthy. The live checks again passed authenticated discovery, all
46 read-only tools, unauthenticated/invalid-token denial, HTTP 403 write denial,
a one-item Pro inventory read, and all nine documentation lookups including
schema extraction. Upstream `execute-request` remained blocked.

The 254-test offline suite passed separately on Python 3.10.22, 3.13.14 and
3.14.8. Lint, skill validation and local Markdown link checks passed.
No tenant mutations were performed. The two Platform list probes still reported
unconfigured: all four `JAMF_PLATFORM_*` variables were absent from `.env`,
`.env.local` and the recreated container. Existing Pro credentials were present.

After the subsequent client-helper and prompt cleanup, the full 254-test suite
and lint passed again on the local Python 3.13 environment. All four prompt
names were retrieved through MCP. The rebuilt Compose service remained healthy,
and the same live Pro, nine-tool docs, authentication and write-denial checks
passed again. Platform list reads still reported unconfigured. No tenant
mutations were performed.


### Container vulnerability scan on 7 October 2026

Grype 0.120.1 scanned the built image with its database from 6 October 2026.
The initial Python 3.12 image had 172 package matches across 80 advisories.
The first runtime update used Python 3.13.16, copied the application from a
separate build stage, and excluded pip, uv, source checkout and build caches.
The MIT license remained in the image. That scan reported:

| Severity | Package matches | Distinct advisories |
| --- | --- | --- |
| High | 55 | 14 |
| Medium | 50 | 25 |
| Low | 10 | 5 |
| Negligible | 46 | 25 |
| Total | 161 | 69 |

These are scanner matches, not validated exploit paths. Of the 161 matches,
159 concern Debian packages: 106 have `wont-fix` status and 53 have `not-fixed`
status in the database. Two Python matches remain, `CVE-2025-15367` and
`CVE-2026-12345`; the database lists fixes only on Python 3.15 for those records.
Their applicability and backport status need review. No installed application
Python dependency matched an advisory. This scan does not establish that the
image is vulnerability-free, and no remaining advisory has been suppressed.

The tested image ID was
`sha256:e96fab0ec9d62be18ce43eea4fb99869955720058183e67e024d3d25f9b0bff2`.
The raw local report is `.docker-local/grype-2026-10-07.json`, ignored by Git.
The scanner image digest was
`sha256:e4a44ef45d285b829ce6efe2642980329661bd2d18eab5fc539138d4adaebbbe`.
To repeat the image scan without granting the scanner access to Docker's socket:

```bash
mkdir -p .docker-local/scan
docker image save jamf-mcp-jamf-mcp:latest -o .docker-local/scan/image.tar
docker run --rm -v "$PWD/.docker-local/scan:/scan" anchore/grype@sha256:e4a44ef45d285b829ce6efe2642980329661bd2d18eab5fc539138d4adaebbbe docker-archive:/scan/image.tar -o json --file /scan/grype.json
```

The scanner downloads its current database, so later results can change.
[Grype documentation](https://oss.anchore.com/docs/installation/grype/)
describes the official scanner distribution.

The final Python 3.13.16 runtime passed all nine live documentation calls,
Pro inventory, HTTP 401 admission checks and HTTP 403 write denial. Pip and uv
were absent. The 254-test offline suite and lint also passed on Python 3.13.16.
Platform credentials remain unconfigured; those live reads are still pending.


### Vulnerability remediation on 7 October 2026

The runtime now uses digest-pinned Python 3.13.16 on Alpine 3.24. Debian's
package population has been replaced, zlib is upgraded to `1.3.2-r1` with its
vendor security patch, and the unused BusyBox shell and TLS client are removed.
The two Python fixes are backported into the shipped standard library, with an
additional no-follow permission-reset fix. See
[patch sources and maintenance](../docker/SECURITY_PATCHES.md).

The first unsuppressed Alpine scan reported three matches, down from 161:

| Match | Resolution evidence |
| --- | --- |
| `CVE-2026-85091`, zlib, High | Alpine `1.3.2-r1` includes the vendor patch; the database predates that package revision |
| `CVE-2025-15367`, Python, Medium | Backported POP3 control-character rejection; injection and printable-command tests passed |
| `CVE-2026-12345`, Python, Medium | Backported descriptor-based cleanup and closed remaining permission-reset races; deletion, permission and legitimate-cleanup tests passed |

The matches persist because the scanner uses package/interpreter version
metadata, which does not describe these installed backports. No matches were
hidden with ignore rules. The tested image ID was
`sha256:588038a3c2a53738bd01e875d72dffb91006ac96fd4ad3c90f1e5b116da644db`.
The raw scan and verification report are retained in the local Codex Security
artifact collection. This records resolution of the known report, not a claim
that the image can have no undiscovered vulnerability.

All 260 tests and 68 subtests passed in a disposable Alpine development
container as a nonroot user. The six security tests also passed inside the exact
deployed runtime. The unpatched image failed the POP3 and cleanup attack cases;
the upstream-only cleanup patch failed the additional permission-reset test.
The final runtime passed those same attacks and ordinary command/cleanup controls.

Live Pro inventory and all nine documentation tools passed again. Admission
checks returned HTTP 401 for missing or invalid tokens, and writes were denied
with HTTP 403. TLS trust retained 124 public roots, and zlib, gzip and ZIP round
trips passed. Platform live reads remain pending separate credentials. No tenant
mutations were performed.


### Final dependency scan and project rename on 7 October 2026

The refreshed Grype database, built on 7 October, recognizes the installed zlib
fix. The image scan now reports two Medium Python version matches. Both fixes
are shipped as backports, and all six container security regressions passed.
No advisories were suppressed. The application dependency audit checked all 45
locked external package/version records, including development dependencies and
the Python 3.10 alternate resolution, with zero known vulnerabilities or skips.

The project, command, server identity and Compose project are named `jamf-mcp`.
The upstream repository remains a Git history reference. Publishing to a private
GitHub repository is a separate step.

After the rename, offline checks passed 254 tests with six host-only skips and
lint passed. The rebuilt service passed TLS admission, authenticated discovery,
the 46-tool read-only catalogue and direct write denial. All six security tests
passed inside the container. All nine live documentation tools passed using the
current `/v4/computers-inventory` specification path, and the adapter rejected
`execute-request`. The first Pro read after restarting failed because
the container lacked Pro credentials. The old checkout path remains a local
compatibility symlink for Codex and the existing 1Password mount. Restoring the
credential injection and repeating the Pro inventory probe were required at
that point. The following record documents their successful completion.

### Credential mount restored on 8 October 2026

The `Jamf MCP read-only` 1Password Environment is now mounted directly at the
renamed checkout's `.env` path. After recreating Compose, all three required Pro
variables were present. No credential values or tenant response bodies were
printed or stored in the repository.

The live Pro inventory read passed through the authenticated MCP endpoint,
resolving the pending tenant check after the rename. TLS admission,
authenticated discovery, setup status and the 46-tool read-only catalogue
passed. A direct write call received HTTP 403 before execution. All six
container security tests passed again.

Documentation specification discovery, endpoint details and response-schema
reads passed using `/v4/computers-inventory`. Upstream `execute-request` remained
blocked. Platform, Protect, Security Cloud and external gateway/OAuth validation
were not tested in this run. No tenant mutations were performed.
