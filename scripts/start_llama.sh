#!/usr/bin/env bash
# Starts llama-server with Qwen 2.5 7B Q4_K_M on port 8080.
# Requires llama.cpp to be built and a GGUF model to be downloaded.
# Override paths with environment variables if needed.

LLAMA_SERVER="${LLAMA_SERVER:-$HOME/llama.cpp/build/bin/llama-server}"
MODEL="${LLAMA_MODEL:-$HOME/llama.cpp/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf}"
PORT="${LLAMA_PORT:-8080}"
CTX="${LLAMA_CTX:-8192}"
GPU_LAYERS="${LLAMA_GPU_LAYERS:-99}"

if [[ ! -f "$LLAMA_SERVER" ]]; then
    echo "Error: llama-server not found: $LLAMA_SERVER"
    echo "Set LLAMA_SERVER=/path/to/llama-server or build llama.cpp."
    exit 1
fi

if [[ ! -f "$MODEL" ]]; then
    echo "Error: model not found: $MODEL"
    echo "Set LLAMA_MODEL=/path/to/model.gguf or download a model."
    exit 1
fi

echo "[llama] Starting $MODEL on port $PORT (GPU layers: $GPU_LAYERS)"
exec "$LLAMA_SERVER" \
    -m "$MODEL" \
    --port "$PORT" \
    --host 127.0.0.1 \
    -c "$CTX" \
    -ngl "$GPU_LAYERS"
