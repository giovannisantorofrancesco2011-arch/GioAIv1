#!/usr/bin/env bash
# vLLM (GPU NVIDIA, Linux/WSL2): massimo throughput con più agenti in parallelo.
#   pip install vllm
#   ./deploy/vllm.sh               → http://localhost:8001/v1
# Poi in settings.yaml: default_backend: vllm  (i nomi serviti coincidono con quelli del profilo)
set -euo pipefail
MODEL="${MODEL:-Qwen/Qwen2.5-Coder-7B-Instruct-AWQ}"        # 24GB: Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8
SERVED="${SERVED:-qwen2.5-coder:7b}"                        # deve combaciare con il tier `main` del profilo
DRAFT="${DRAFT:-Qwen/Qwen2.5-Coder-0.5B-Instruct}"          # speculative decoding: stesso tokenizer

ARGS=(
  --port 8001
  --served-model-name "$SERVED"
  --max-model-len 16384
  --gpu-memory-utilization 0.90
  --enable-prefix-caching                 # riusa la KV cache del prefisso comune (persona + ruolo)
  --enable-auto-tool-choice --tool-call-parser hermes   # function calling per i tool nativi
)
if [[ "${SPECULATIVE:-1}" == "1" ]]; then
  ARGS+=(--speculative-config "{\"model\": \"$DRAFT\", \"num_speculative_tokens\": 5}")
fi
exec vllm serve "$MODEL" "${ARGS[@]}"
