#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$DIR/.venv/bin/activate"

source "$VENV"

echo "=== ruff check ==="
ruff check "$DIR" --fix "$@"

echo "=== ruff format ==="
ruff format "$DIR" "$@"
