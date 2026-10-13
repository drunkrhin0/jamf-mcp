# Container security patches

The image applies CPython backports and uses Alpine's patched zlib. Keep this
note with the patch files so a base-image update does not silently remove fixes.
Build both stages from the same base for compatible musl wheels.

## Patch sources

| File or package | Source and behavior |
| --- | --- |
| `patches/CVE-2025-15367.patch` | [CPython PR 143924](https://github.com/python/cpython/pull/143924); POP3 rejects control characters before sending commands |
| `patches/CVE-2026-12345.patch` | [Python 3.13 backport](https://github.com/python/cpython/pull/158429); directory cleanup uses open descriptors during permission-error recovery |
| `patches/CVE-2026-12345-nofollow.patch` | Repository fix for remaining fallback/root races; permission resets refuse symlink traversal |
| zlib `1.3.2-r1` or later | [Alpine recipe](https://github.com/alpinelinux/aports/blob/3.24-stable/main/zlib/APKBUILD); vendor fix for `CVE-2026-85091` |

CPython copyright and licence remain in the base image. The no-follow adjustment
targets Linux. If the OS cannot safely reset permissions, cleanup raises
`OSError`; `ignore_cleanup_errors` retains its existing handling. Replace
backports with a fixed stable base only after the regressions pass.

## Verify the runtime

Run the six security regressions as the container's nonroot user:

```bash
docker compose --env-file .env.local exec -T -e JAMF_MCP_CONTAINER_SECURITY=1 jamf-mcp python - < tests/test_container_security.py
```

They cover POP3 commands, deletion/permission races and ordinary restricted-directory
cleanup. Host interpreters skip these tests because they lack the patches.
After a base or dependency change, run the full suite in an Alpine development
container and repeat the [MCP read probes](../docs/DOCKER.md).

## Scan the image

Export the image so the scanner does not need the Docker socket:

```bash
mkdir -p .docker-local/scan
docker image save jamf-mcp-jamf-mcp:latest -o .docker-local/scan/image.tar
docker run --rm -v "$PWD/.docker-local/scan:/scan" anchore/grype@sha256:e4a44ef45d285b829ce6efe2642980329661bd2d18eab5fc539138d4adaebbbe docker-archive:/scan/image.tar -o json --file /scan/grype.json
```

This is the recorded scanner digest. Its downloaded database can change. Retain
all matches and the raw report; classify version warnings against installed
backports and regression evidence rather than adding ignore rules. Record the
image ID and scanner/database versions in [Validation](../docs/VALIDATION.md).
