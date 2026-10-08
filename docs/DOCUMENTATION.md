# Documentation lookup

Jamf MCP includes nine documentation tools alongside its Jamf management tools.
The former standalone `jamf_docs_mcp` package has been folded into
`src/jamf_mcp/tools/docs.py`. Existing docs tool names are preserved; configure
one Jamf MCP connection instead of a separate `jamf-docs-mcp` connection.

## Run

The default server includes all products and documentation:

```bash
uv run jamf-mcp
```

For documentation alone, plus the two setup tools:

```bash
uv run jamf-mcp --products docs --read-only
```

`docs` and `jamf_docs` select the same catalogue. Documentation tools belong to
the `api` tool category, so `--tool-filter complex` excludes them. The repository's
Compose service includes `pro platform docs`; follow [Local Docker](LOCAL_DOCKER.md)
for its TLS and authentication setup. Rebuild the image after updating the code.

## Use

1. Call `list_available_specs` to discover current specification titles.
2. Call `search_jamf_api` with a pattern such as `blueprints` or `computers`.
3. Call `get_endpoint_details` with the returned path, HTTP method and spec title.
4. Use `get_request_body_schema` or `get_response_schema` to inspect payloads.

The upstream titles include a namespace, such as `jamf-pro=Jamf Pro API` and
`platform-api=Blueprints API`. The original `Jamf Pro API` and `Classic API`
shorthand still works. Use paths returned by `list_api_endpoints`; upstream
OpenAPI paths can omit `/api` or `/JSSResource`.

Documentation lookup connects to the public service at
`https://developer.jamf.com/mcp`. It uses no tenant credentials and forwards no
inbound authentication token. Network access is required when a tool is called;
startup and local discovery do not contact that service. Setup status does not
verify upstream access.

## Results and access

Forwarded results retain upstream text, images, structured data, metadata and
error status. Schema tools extract the request body or selected response from
`get-endpoint`, retaining components for schema references and upstream metadata.
A missing documented body or response is reported as an execution error. Local
connection or validation failures set MCP `isError` and include structured error
details. Documentation results need not contain the
management tools' `success` field.

Remote callers use the main endpoint's authentication and `jamf:read` scope.
The documentation adapter permits only its explicit documentation allowlist,
including specification lookup, endpoint search and server variables. It rejects
`execute-request` and other unapproved operations. Looking up a POST or DELETE schema does not
execute that operation against a tenant.

The upstream tool list is cached in memory. `refresh_jamf_docs_cache` refreshes
that list; endpoint content is fetched on demand. Offline tests mock upstream
access and exercise these tools through the main MCP interface.
