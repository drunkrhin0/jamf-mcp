#!/usr/bin/env bash
# Compatibility entry point for the shared offline checks.
set -euo pipefail
cd "$(dirname "$0")"
if [[ "$#" -ne 0 ]]; then
    echo "Use docs/LOCAL_DOCKER.md for read-only live checks." >&2
    exit 2
fi
exec ./scripts/check.sh
