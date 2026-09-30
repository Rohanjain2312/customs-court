#!/usr/bin/env bash
# Serve the free local models with llama.cpp (OpenAI-compatible API on localhost).
# Zero cost: open weights (Apache-2.0) run on this machine, no API key, no network after download.
#
#   bash scripts/local_llm.sh start      # 4B on :8081, 2B on :8082
#   bash scripts/local_llm.sh stop
#
# One-time setup (both free):
#   llama.cpp release build b11265 (macos-arm64) in ~/.local/opt/llama
#   huggingface.co/unsloth/Qwen3.5-4B-GGUF  Qwen3.5-4B-Q4_K_M.gguf (2.74 GB)
#   huggingface.co/unsloth/Qwen3.5-2B-GGUF  Qwen3.5-2B-Q4_K_M.gguf (1.28 GB)
set -euo pipefail
BIN="${LLAMA_BIN:-$HOME/.local/opt/llama/llama-b11265/llama-server}"
MODELS="${LOCAL_MODELS_DIR:-$HOME/.local/share/models}"
LOGS="data/logs"
mkdir -p "$LOGS"

serve() { # name file port ctx
  "$BIN" -m "$MODELS/$2" --port "$3" --host 127.0.0.1 -c "$4" -np 1 -ngl 99 -fa on \
    --jinja --cache-type-k q8_0 --cache-type-v q8_0 --cache-reuse 256 --metrics \
    > "$LOGS/llama-$1.log" 2>&1 &
  echo $! > "$LOGS/llama-$1.pid"
  for _ in $(seq 1 120); do
    curl -sf "http://127.0.0.1:$3/health" >/dev/null && { echo "$1 ready on :$3"; return 0; }
    sleep 1
  done
  echo "$1 did not start; see $LOGS/llama-$1.log" >&2
  return 1
}

case "${1:-start}" in
  start)
    serve qwen3.5-4b Qwen3.5-4B-Q4_K_M.gguf 8081 "${CTX_4B:-32768}"
    if [ "${ONLY_4B:-0}" != "1" ]; then serve qwen3.5-2b Qwen3.5-2B-Q4_K_M.gguf 8082 "${CTX_2B:-32768}"; fi
    ;;
  stop)
    for f in "$LOGS"/llama-*.pid; do [ -f "$f" ] && kill "$(cat "$f")" 2>/dev/null; rm -f "$f"; done
    echo stopped
    ;;
esac
