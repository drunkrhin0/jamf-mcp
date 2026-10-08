#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

run_python() {
    if [[ -n "${PYTHON:-}" ]]; then
        "$PYTHON" "$@"
    else
        uv run --frozen python "$@"
    fi
}

run_python -m pytest -q
run_python -m ruff check \
    src/jamf_mcp/server.py \
    src/jamf_mcp/remote.py \
    src/jamf_mcp/platform_client.py \
    src/jamf_mcp/tools/platform.py \
    src/jamf_mcp/tools/device_reporting.py \
    src/jamf_mcp/tools/_registry.py \
    src/jamf_mcp/tools/docs.py \
    scripts/validate_remote.py \
    tests
