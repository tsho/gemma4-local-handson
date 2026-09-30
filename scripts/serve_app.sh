#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="${UV_CACHE_DIR:-.cache/uv}"
exec uv run --frozen uvicorn gemma_demo.main:create_app --factory \
  --host 127.0.0.1 --port "${APP_PORT:-8000}" "$@"
