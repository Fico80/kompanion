#!/bin/bash
# Local Assistant Launcher

# Exit on unset variables, but not on every error (pip warnings would abort the script)
set -u

# Change to the script's directory
cd "$(dirname "$0")"

echo "==========================================="
echo "   Starting Local Assistant...             "
echo "==========================================="

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "[*] Creating Python virtual environment (venv)..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "[*] Activating virtual environment..."
source venv/bin/activate

# Install/update dependencies only when requirements changed
REQ_HASH_FILE="venv/.requirements.sha256"
REQ_HASH="$(sha256sum requirements.txt | awk '{print $1}')"
OLD_REQ_HASH=""
if [ -f "$REQ_HASH_FILE" ]; then
    OLD_REQ_HASH="$(cat "$REQ_HASH_FILE")"
fi

if [ "$REQ_HASH" != "$OLD_REQ_HASH" ]; then
    echo "[*] Installing/updating Python dependencies..."
    pip install --upgrade pip -q
    # openwakeword needs --no-deps: tflite-runtime is unavailable on Python 3.13+
    # We use the ONNX backend (onnxruntime) which is installed via requirements.txt
    pip install openwakeword --no-deps --no-warn-conflicts -q
    pip install -r requirements.txt --no-warn-conflicts -q
    printf "%s\n" "$REQ_HASH" > "$REQ_HASH_FILE"
else
    echo "[*] Python dependencies unchanged."
fi

# Set trap to clean up the backend process when this script is closed/terminated
cleanup() {
    echo ""
    echo "[*] Stopping background processes..."
    if [ ! -z "$SERVER_PID" ]; then
        kill "$SERVER_PID" 2>/dev/null || true
    fi
    if [ ! -z "$LISTENER_PID" ]; then
        kill "$LISTENER_PID" 2>/dev/null || true
    fi
    if [ ! -z "$REMINDER_PID" ]; then
        kill "$REMINDER_PID" 2>/dev/null || true
    fi
    if [ ! -z "${LLAMA_PID:-}" ]; then
        kill "$LLAMA_PID" 2>/dev/null || true
    fi
    if [ ! -z "${WHISPER_PID:-}" ]; then
        kill "$WHISPER_PID" 2>/dev/null || true
    fi
    echo "[*] Assistant stopped successfully."
    exit
}
trap cleanup SIGINT SIGTERM

# Kill any leftover processes before starting fresh.
pkill -f "python3 backend/main.py" 2>/dev/null || true
pkill -f "python3 scripts/listener.py" 2>/dev/null || true
pkill -f "python3 scripts/reminder_daemon.py" 2>/dev/null || true
sleep 0.5

# Also free port 8000 if still occupied
if which lsof >/dev/null 2>&1; then
    OLD_PID=$(lsof -t -i:8000 2>/dev/null)
    if [ -n "$OLD_PID" ]; then
        echo "[*] Port 8000 is still occupied (PID $OLD_PID). Stopping it..."
        kill "$OLD_PID" 2>/dev/null || true
        sleep 0.5
    fi
fi

# Load .env for local AI server detection
if [ -f .env ]; then
    set -a; source .env; set +a
fi

# Start llama-server if LLM_BASE_URL points to localhost and binary exists
LLAMA_PID=""
if echo "${LLM_BASE_URL:-}" | grep -qE "127\.0\.0\.1|localhost"; then
    LLAMA_BIN="${LLAMA_SERVER:-$HOME/llama.cpp/build/bin/llama-server}"
    LLAMA_MDL="${LLAMA_MODEL:-$HOME/llama.cpp/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf}"
    LLAMA_PORT=$(echo "${LLM_BASE_URL:-8080}" | grep -oP ':\K\d+' | head -1)
    LLAMA_PORT="${LLAMA_PORT:-8080}"
    if [ -f "$LLAMA_BIN" ] && [ -f "$LLAMA_MDL" ]; then
        if ! lsof -i:"$LLAMA_PORT" >/dev/null 2>&1; then
            echo "[*] Starting llama-server on port $LLAMA_PORT..."
            "$LLAMA_BIN" -m "$LLAMA_MDL" --port "$LLAMA_PORT" --host 127.0.0.1 \
                -ngl "${LLAMA_GPU_LAYERS:-99}" -c "${LLAMA_CTX:-8192}" --parallel 1 \
                > /tmp/llama-server.log 2>&1 &
            LLAMA_PID=$!
            sleep 3
        else
            echo "[*] llama-server is already running on port $LLAMA_PORT."
            echo "    If you changed LLAMA_CTX, stop the existing llama-server before restarting Kompanion."
        fi
    fi
fi

# Start whisper-server if WHISPER_BASE_URL points to localhost and binary exists
WHISPER_PID=""
if echo "${WHISPER_BASE_URL:-}" | grep -qE "127\.0\.0\.1|localhost"; then
    WHISPER_BIN="${WHISPER_SERVER:-$HOME/whisper.cpp/build/bin/whisper-server}"
    WHISPER_MDL="${WHISPER_MODEL:-$HOME/whisper.cpp/models/ggml-large-v3-turbo.bin}"
    WHISPER_PORT=$(echo "${WHISPER_BASE_URL:-8081}" | grep -oP ':\K\d+' | head -1)
    WHISPER_PORT="${WHISPER_PORT:-8081}"
    WHISPER_LANG="${WHISPER_LANGUAGE:-en}"
    if [ -f "$WHISPER_BIN" ] && [ -f "$WHISPER_MDL" ]; then
        if ! lsof -i:"$WHISPER_PORT" >/dev/null 2>&1; then
            echo "[*] Starting whisper-server on port $WHISPER_PORT..."
            "$WHISPER_BIN" -m "$WHISPER_MDL" -l "$WHISPER_LANG" \
                --host 127.0.0.1 --port "$WHISPER_PORT" \
                > /tmp/whisper-server.log 2>&1 &
            WHISPER_PID=$!
            sleep 2
        else
            echo "[*] whisper-server is already running on port $WHISPER_PORT."
        fi
    fi
fi

# Start FastAPI server in the background
echo "[*] Starting FastAPI backend at http://127.0.0.1:8000..."
python3 backend/main.py &
SERVER_PID=$!

# Start speech hotkey overlay listener in the background
echo "[*] Starting Kompanion voice overlay in the background..."
# Pass --wakeword flag if WAKE_WORD_ENABLED=1 is set in .env
WAKEWORD_FLAG=""
if grep -qE "^WAKE_WORD_ENABLED=1" .env 2>/dev/null; then
    WAKEWORD_FLAG="--wakeword"
    echo "[*] Wake-word mode enabled (WAKE_WORD_ENABLED=1 in .env)"
fi
python3 scripts/listener.py $WAKEWORD_FLAG &
LISTENER_PID=$!

# Start reminder daemon in the background
echo "[*] Starting reminder daemon..."
python3 scripts/reminder_daemon.py &
REMINDER_PID=$!

# Wait a moment for uvicorn to boot up
sleep 1.5

echo "==========================================="
echo " Assistant is running. Press [Ctrl+C] to stop."
echo "==========================================="

# Wait for the background backend process
wait "$SERVER_PID"
