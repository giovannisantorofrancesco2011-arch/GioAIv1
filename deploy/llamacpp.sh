#!/usr/bin/env bash
# llama.cpp llama-server: il più leggero ed efficiente su GPU piccole, Apple Silicon e CPU.
#   brew install llama.cpp   |   winget install llama.cpp   |   build da https://github.com/ggml-org/llama.cpp
#   ./deploy/llamacpp.sh      → http://localhost:8080/v1   (settings.yaml: default_backend: llamacpp)
set -euo pipefail
MAIN="${MAIN:-Qwen/Qwen2.5-Coder-7B-Instruct-GGUF:Q4_K_M}"
DRAFT="${DRAFT:-Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF:Q8_0}"
ALIAS="${ALIAS:-qwen2.5-coder:7b}"   # nome esposto: deve combaciare con il tier `main`

exec llama-server \
  -hf "$MAIN" \
  --alias "$ALIAS" \
  --port 8080 \
  -c 16384 \
  -ngl 99 \
  --flash-attn on \
  -ctk q8_0 -ctv q8_0 \
  --cache-reuse 256 \
  -np 3 \
  --jinja \
  -hfd "$DRAFT" --draft-max 16 --draft-min 4
# Opzioni:
#   -ngl 99           tutti i layer in GPU (riduci se la VRAM non basta; 0 = solo CPU)
#   --flash-attn on   su build vecchie usa semplicemente -fa
#   -ctk/-ctv q8_0    KV cache quantizzata: metà memoria, qualità praticamente identica
#   --cache-reuse     riusa il prefisso in cache tra richieste (persona + prompt di ruolo)
#   -np 3             3 slot paralleli (agenti in parallelo)
#   -hfd ...          modello draft per speculative decoding (1.5–2.5x più veloce sul codice)
#   --jinja           template chat ufficiale → function calling per i tool nativi
