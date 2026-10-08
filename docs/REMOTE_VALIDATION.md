# Remote deployment validation

This repository targets reusable local and remote deployments. Provider and
hosting selection are deployment-time choices; no infrastructure is required to
build or test it locally. Local stdio uses server-held
Jamf API client credentials; that mode remains available. OAuth is the default
remote mode. Scoped bearer credentials provide an alternative for gateways.
Neither mode forwards caller credentials to Jamf.

## Deployment patterns

- Local stdio: credentials stay in the server process; no remote auth settings.
- Direct remote OAuth: default `JAMF_MCP_REMOTE_AUTH_MODE=oauth`; configure
  resource URL and external issuer. The current adapter verifies RS256 JWTs.
- Gateway connection: `JAMF_MCP_REMOTE_AUTH_MODE=bearer`; the gateway holds a
  scoped upstream token while its own policy controls access to the gateway.
  The MCP server still enforces the token's configured scopes. It does not trust
  arbitrary identity headers or accept unauthenticated remote calls.

Bearer configuration uses the public HTTPS `JAMF_MCP_RESOURCE_URL` plus secret
`JAMF_MCP_BEARER_TOKENS_JSON`. Supply an array of records with unique identities
and tokens, for example this template (replace the deliberately invalid token):

```json
[{"identity":"gateway-reader","token":"REPLACE_WITH_RANDOM_SECRET","scopes":["jamf:read"]}]
```

Generate each token with `python -c 'import secrets; print(secrets.token_urlsafe(32))'`
on your own machine, then store it through your secret manager. Tokens must be at
least 32 characters and scopes must include `jamf:read`. Add `jamf:write` and
`jamf:admin` only where needed. Rotate/revoke by changing the configured records
and restarting the server, then update the gateway credential. Tokens are shared
service identities, not individual Jamf accounts; static tokens do not expire
automatically. Issuer/audience values apply only to OAuth mode.

Cloudflare MCP portals support OAuth and bearer upstream credentials. Gateway
routing requires Streamable HTTP, already provided by this server. The gateway
can authenticate its users separately; a shared upstream token does not convey
individual user identity to this server.
[Cloudflare MCP portals](https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/).

## Decisions and configuration

When deploying, record the applicable choices below. They are not prerequisites
for finishing this reusable codebase. The issuer/client-flow items apply to OAuth
mode; bearer mode requires gateway credential provisioning instead:

- Who may use the server and whether server-held Jamf permissions are appropriate
  for everyone in that group. Current remote mode uses one configured Jamf
  connection; individual Jamf logins need a separate implementation.
- The authorization server's HTTPS issuer URL. It must issue RS256 access tokens
  with the intended audience and `jamf:read`, `jamf:write`, `jamf:admin` scopes.
  Grant read initially; mutations require read plus write and API administration
  also requires admin. The provider must enforce who may obtain each scope.
- The hosting target and stable public HTTPS MCP URL. Configure TLS at the proxy
  and pass the configured public Host header to the process. Use one server
  instance per Jamf credential set.
- How the chosen MCP host registers its OAuth client: pre-registration, supported
  client metadata, or dynamic registration. Configure authorization-code/PKCE,
  exact redirect URLs and any refresh-token policy in the provider according to
  that host's current instructions.

If choosing Okta, use an authorization server intended for your own API; its
custom-server support and production entitlement need verification in your org.
[Okta authorization servers](https://developer.okta.com/docs/concepts/auth-servers/),
[OpenAI auth](https://developers.openai.com/plugins/build/auth)

Configure the public values and backend credentials in a private environment
file, using `.env.example` as the variable reference. Then start the process:

```bash
uv run --env-file .env jamf-mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

Use another bind address only when your selected proxy/network requires it.
`JAMF_MCP_RESOURCE_URL` must match the public endpoint path, not the internal
HTTP address. `JAMF_MCP_OAUTH_AUDIENCE` defaults to that URL; set it when the
provider intentionally uses a different resource identifier.

## Public endpoint probe

Run from a machine that can reach the public HTTPS endpoint:

```bash
uv run --env-file .env python scripts/validate_remote.py
```

OAuth mode checks protected-resource metadata and an unauthenticated read-scope
401 challenge. Bearer mode skips OAuth metadata and checks the same admission
and read operations; pass `--auth-mode bearer` or set the mode environment value. It reports authenticated checks as pending until a short-lived
provider access token is supplied in `JAMF_MCP_VALIDATION_TOKEN`. Use your existing
secret injection mechanism for that token; the probe prints neither tokens nor
response bodies. It then checks modern discovery, the tool catalogue, and the
read-only setup-status tool. It executes no Jamf mutation.

This probe is a transport check, not an OAuth login-flow test. In OAuth mode, the token must
come from the selected provider's intended client flow. In bearer mode, supply
a configured scoped credential in `JAMF_MCP_VALIDATION_TOKEN`; the probe does
not need the server's token-record JSON. Avoid treating a manually
supplied token as evidence that account linking works.

### Opt-in backend reads through MCP

Setup status reports configuration; it does not contact Jamf. To verify a
configured product's credentials, permissions and API path, supply a validation
token and select that product explicitly:

```bash
uv run --env-file .env python scripts/validate_remote.py --backend jamf_pro
# Repeat --backend for each configured product:
uv run --env-file .env python scripts/validate_remote.py --backend jamf_protect --backend jamf_security
```

The fixed calls are `jamf_get_computer(page=0, page_size=1)`,
`jamf_protect_list_computers(limit=1)` and
`jamf_get_risk_devices(page=0, page_size=1)` (Security API v1). Protect's tool
fetches its computer list before applying the limit, so the limit does not bound
upstream data transfer. Select only products you intend to validate. Missing
validation credentials fail before any requests; unconfigured products and
failed backend calls fail the probe. Repeated selections run once per product.
The probe prints tool names and pass status, never tenant response bodies.

These checks exercise real backend reads when run against a live deployment.
Offline probe tests use mocked responses and prove request selection and result
handling only. Keep backend-read evidence separate from transport, OAuth login
and gateway access-policy evidence; each needs its own recorded outcome.

## Live acceptance cases

Start with one read-only identity and one configured product on a disposable
tenant. In the intended MCP client, discover the catalogue and call the same
product read listed above. Verify the result against a known tenant record or
the tenant's own API response, including an empty-list case when appropriate.
Record the client, authentication path, tool and result category. This validates
the user journey from client through authentication to Jamf; setup status and a
manually supplied access token alone do not establish that journey.

Then exercise these failure cases on that test deployment:

| Case | Expected behavior and evidence |
|------|--------------------------------|
| Reader attempts a write | Server rejects the call with insufficient scope before any Jamf mutation. Confirm the denial in the client and correlate it with server/backend request evidence. Stop at the denial; do not approve scope escalation or retry with a writer during this check. |
| Removed static bearer token | Remove its server record, restart every server instance, and retry with the old gateway credential. Expect HTTP 401; provision a replacement credential separately. |
| Expired OAuth access token | Expect HTTP 401 for the expired token. Separately verify the intended client's refresh/login behavior with a valid authorization grant. |
| Provider-revoked OAuth grant | Record when the provider stops issuing or refreshing tokens and when existing access stops working. This verifier checks JWT signatures and expiry using cached JWKS; it has no token introspection or revocation list. Existing valid JWTs may remain accepted until expiry. Immediate revocation requires a separately implemented mechanism. |
| Jamf account lacks read privileges | Use a restricted test backend account and call the selected read through MCP. Expect an error-marked tool result, not successful empty data. Check that the actual client presents the failure clearly. |
| Private data in logs | Review server, proxy, gateway and client logs for the failure cases. Tokens, Authorization headers, credentials and upstream response bodies must not be captured. Disable request/response-body tracing and credential-bearing debug logs in deployment components. Record pass/fail without copying private content into the report. |

The probe remains read-only and does not automate attempted writes, credential
rotation or provider administration. These negative cases need separate live
evidence. Independent review is required for changes to these consequential
boundaries. Follow [Development](DEVELOPMENT.md) for repository checks.

## Inspector and actual host (OAuth)

Walk the authorization-code flow in [MCP Inspector](https://modelcontextprotocol.io/docs/2026-07-28/tools/inspector/authorization),
then [connect the endpoint in the intended OpenAI host](https://developers.openai.com/plugins/deploy/connect-chatgpt).
Verify initial sign-in requests read access only; approved reads succeed;
unapproved identities are denied; and token expiry/refresh behaves as configured.

Test a read-only account's write denial using a disposable Jamf tenant. Confirm
HTTP 403 includes the required scope and discovery URL, and the host consumes
the `mcp/www_authenticate` signal. This implementation supplies that signal in
an error-marked JSON-RPC result on HTTP 403; actual host behavior must establish
whether account linking/step-up works with that response. Record host/version
and result rather than assuming mock tests establish this.

For allowed mutations, inspect the proposed operation and host confirmation on
a disposable tenant before executing it. Validate consequential tool behavior,
Jamf privileges and inventory API availability against that tenant's version.
Production write testing requires a separately agreed operation and rollback.

## Gateway validation (bearer)

When you deploy, add the HTTPS MCP URL and a scoped bearer credential to your
selected gateway. For Cloudflare, configure the upstream server with bearer
authentication. Test discovery, tool calls, the gateway's access policy, denied
mutations with a reader token, and revoked tokens. Confirm the gateway can reach
the server and forwards the configured Host header. Static credentials have no
OAuth linking or step-up flow; changing scopes requires changing token records
and gateway credentials. A direct OpenAI OAuth connection should use OAuth mode.
Live Cloudflare validation is deferred until an actual deployment exists.

## Evidence to retain

Record validation date, commit/patch identifier, Python/SDK versions, provider
issuer and configured audience, public endpoint, host/version, OAuth flow
outcomes, requested/granted scope sets, and selected live read/write cases.
Keep tokens and Jamf credentials out of the report. Mark any untested step as
pending. The offline suite and local TLS/bearer deployment have been validated,
including Pro inventory and documentation reads. See
[Local Docker](LOCAL_DOCKER.md#current-validation-status) for that evidence.
No public endpoint, live OAuth linking or external gateway policy has been
validated.

## Jamf Platform probes

After configuring the [separate Platform integration](PLATFORM_SETUP.md), use
`--backend jamf_platform` for a one-item Blueprint read and
`--backend jamf_platform_compliance` for the benchmark list. These reads
validate their respective permissions separately. DDM reporting still needs
an existing Platform device UUID or declaration identifier and a nonempty
filter; neither list probe establishes `declarations:read` access.
