# Docker setup

This Compose service runs Jamf MCP with Jamf Pro, Platform and documentation tools at `https://localhost:8443/mcp`.
Only this machine can connect. Write tools are excluded, and the local bearer
identity has only `jamf:read`. Use a Jamf API client whose assigned API roles
grant only the reads you intend to test.

Documentation uses the same endpoint and local reader token. It needs no tenant
credentials, and makes outbound requests to `https://developer.jamf.com/mcp`
only when a documentation tool is called. No second container is required.

## Current validation status

Local Pro inventory and documentation reads passed on 13 October 2026.
Platform, Protect and Security Cloud live access remains unverified. The
[validation record](VALIDATION.md) contains the tested paths and security results.

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

## Connect a client

Use `https://localhost:8443/mcp` with Streamable HTTP and the bearer token from
`.env.local`. Configure the client to trust `.docker-local/server.crt` explicitly.
This setup does not change system certificate trust. The container's outbound
Jamf requests use normal public certificate trust.

For client configuration, see [Installation](INSTALLATION.md#remote-http).
Platform reads need the separate [Jamf Account integration](PLATFORM_SETUP.md).

## Stop or renew the certificate

Stop the service with:

```bash
docker compose --env-file .env.local down
```

To renew the certificate, stop the service, remove `.docker-local/server.crt`
and `.docker-local/server.key`, rerun `scripts/setup_local_docker.py`, and start
the service. The setup script preserves the token in `.env.local`.

## Maintain the image

Follow [Container security patches](../docker/SECURITY_PATCHES.md) when changing
the base image or backports. Rebuild after code or dependency changes, then
repeat the read-only probes above. Record results per product in
[Validation](VALIDATION.md).
