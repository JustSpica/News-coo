#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.venv/bin/activate"

source "$VENV"

if [[ "${1:-}" == "--check" ]]; then
    echo "=== ruff check ==="
    ruff check "$ROOT"

    echo "=== ruff format --check ==="
    ruff format "$ROOT" --check
else
    echo "=== ruff check --fix ==="
    ruff check "$ROOT" --fix

    echo "=== ruff format ==="
    ruff format "$ROOT"
fi
