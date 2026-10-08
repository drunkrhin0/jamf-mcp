# Container security patches

The runtime uses digest-pinned Python 3.13.16 on Alpine. Build both stages from
the same base so native wheels match the runtime's musl libraries. Package
upgrades run during the build; zlib must be at least `1.3.2-r1`.

BusyBox, its shell and TLS client are removed from the runtime. The CA bundle,
base configuration data and a mode-1777 `/tmp` remain. Use Python or the MCP
command when running commands in the container. The build CA is a temporary
build secret; runtime certificate verification stays enabled.

## Python backports

- `patches/CVE-2025-15367.patch` contains the library change from
  [CPython PR 143924](https://github.com/python/cpython/pull/143924). POP3 rejects
  C0 and DEL control characters before sending a command. Printable commands
  retain their existing behavior.
- `patches/CVE-2026-12345.patch` contains the library changes from the official
  [Python 3.13 backport](https://github.com/python/cpython/pull/158429).
  Temporary-directory cleanup uses open directory descriptors when recovering
  from permission errors, preserving ordinary `shutil.rmtree` callbacks.
- `patches/CVE-2026-12345-nofollow.patch` is a repository adjustment. It closes
  the remaining permission-reset fallback and root-path races. Permission
  resets explicitly refuse to follow symlinks. If the OS cannot perform the
  safe reset, cleanup raises `OSError`; `ignore_cleanup_errors` retains its
  existing error handling. This adjustment targets the shipped Linux runtime.

Both upstream patches include only affected library files. Their original
CPython copyright and license remain in the base image. Replace the backports
with a patched stable base when available, then repeat the regression tests.

## Compression library

Alpine's zlib `1.3.2-r1` includes the fix for `CVE-2026-85091`. Its
[package recipe](https://github.com/alpinelinux/aports/blob/3.24-stable/main/zlib/APKBUILD)
records the security fix and bundled upstream patch. An unchanged upstream
version string does not indicate whether a distribution backport is present.

## Verify the shipped runtime

Run the six security tests as the container's nonroot user:

```bash
docker compose --env-file .env.local exec -T -e JAMF_MCP_CONTAINER_SECURITY=1 jamf-mcp python - < tests/test_container_security.py
```

The tests cover POP3 injection and printable commands, deletion and
permission-change races, and cleanup of directories with restricted permissions.
They are skipped in ordinary host tests because the host interpreter is not
patched by this Dockerfile. Run the full suite in an Alpine development container
to verify the native wheels, and repeat the read-only MCP probes in
[Local Docker](../docs/LOCAL_DOCKER.md).

A fresh image scan must retain all matches. Classify version-based matches
against the installed package revision, patch files and regression results;
keep the raw report. Do not add ignore rules to conceal patched-version matches.
