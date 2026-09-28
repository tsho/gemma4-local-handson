#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"
if [[ -z "${LLAMA_SERVER_BIN:-}" ]]; then
  if [[ -f .runtime/b11146/server-path.txt ]]; then
    LLAMA_SERVER_BIN="$PROJECT_ROOT/$(cat .runtime/b11146/server-path.txt)"
  elif command -v llama-server >/dev/null 2>&1; then
    LLAMA_SERVER_BIN="$(command -v llama-server)"
  else
    echo 'Run: uv run python scripts/setup_llamacpp.py' >&2
    exit 1
  fi
fi
MODEL_PATH="${MODEL_PATH:-$PROJECT_ROOT/models/gemma-4-12b-it-qat-q4_0.gguf}"
if [[ ! -f "$MODEL_PATH" ]]; then
  echo "Model missing: $MODEL_PATH" >&2
  exit 1
fi
exec "$LLAMA_SERVER_BIN" \
  --model "$MODEL_PATH" \
  --alias gemma4 \
  --host 127.0.0.1 --port "${INFERENCE_PORT:-8080}" \
  --ctx-size "${CONTEXT_SIZE:-8192}" \
  --n-gpu-layers "${GPU_LAYERS:-99}" \
  --parallel 1 --jinja --reasoning off --reasoning-format deepseek \
  "$@"
