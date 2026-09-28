#!/usr/bin/env bash
set -euo pipefail
if ! command -v vllm >/dev/null 2>&1; then
  echo 'Install vLLM in a separate Linux GPU environment; see docs/setup-linux-gpu.md.' >&2
  exit 1
fi
exec vllm serve "${HF_MODEL:-google/gemma-4-12B-it-qat-w4a16-ct}" \
  --served-model-name gemma4 \
  --host 127.0.0.1 --port "${INFERENCE_PORT:-8080}" \
  --max-model-len "${CONTEXT_SIZE:-8192}" \
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION:-0.85}" \
  --max-num-seqs "${MAX_NUM_SEQS:-1}" \
  --generation-config vllm \
  "$@"
