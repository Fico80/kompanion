# Local AI Setup

This setup runs speech-to-text and LLM calls locally:

- `whisper.cpp` for transcription
- `llama.cpp` for OpenAI-compatible chat completions

No cloud API key is required for this mode.

## llama.cpp

### Build

Example with Vulkan on Fedora:

```bash
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp

sudo dnf install vulkan-devel glslc

cmake -B build -DGGML_VULKAN=1
cmake --build build --config Release -j$(nproc)
```

ROCm can be faster on supported AMD GPUs, but setup is more hardware-specific:

```bash
cmake -B build -DGGML_HIPBLAS=1 -DAMDGPU_TARGETS=gfx1032
cmake --build build --config Release -j$(nproc)
```

### Download a Model

Recommended starting point for 8 GB VRAM:

```bash
mkdir -p ~/llama.cpp/models

huggingface-cli download bartowski/Qwen2.5-7B-Instruct-GGUF \
  Qwen2.5-7B-Instruct-Q4_K_M.gguf \
  --local-dir ~/llama.cpp/models
```

Typical quantization choices:

| Quantization | Approx. VRAM | Notes |
|---|---:|---|
| Q4_K_M | 4.4 GB | good default |
| Q5_K_M | 5.1 GB | better quality |
| Q8_0 | 7.6 GB | near full precision |

### Start llama-server

From the assistant project:

```bash
LLAMA_SERVER=~/llama.cpp/build/bin/llama-server \
LLAMA_MODEL=~/llama.cpp/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
./scripts/start_llama.sh
```

Or start it manually:

```bash
~/llama.cpp/build/bin/llama-server \
  -m ~/llama.cpp/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
  --host 127.0.0.1 \
  --port 8080 \
  -c 4096 \
  -ngl 99
```

### Configure .env

```env
LLM_BASE_URL=http://127.0.0.1:8080/v1
LLM_MODEL=local
```

`/chat/completions` is appended automatically if it is missing.

## whisper.cpp

### Build

```bash
git clone https://github.com/ggml-org/whisper.cpp
cd whisper.cpp

cmake -B build -DGGML_VULKAN=1
cmake --build build --config Release -j$(nproc)
```

### Download a Model

```bash
./models/download-ggml-model.sh large-v3-turbo
```

Smaller and faster option:

```bash
./models/download-ggml-model.sh small
```

### Start whisper-server

```bash
~/whisper.cpp/build/bin/whisper-server \
  -m ~/whisper.cpp/models/ggml-large-v3-turbo.bin \
  -l en \
  --host 127.0.0.1 \
  --port 8081
```

Use `-l de` or set `WHISPER_LANGUAGE=de` if you primarily speak German.

### Configure .env

```env
WHISPER_BASE_URL=http://127.0.0.1:8081
WHISPER_LANGUAGE=en
```

The assistant calls `/inference` for local `whisper.cpp` servers.

## Full Local .env Example

```env
WHISPER_BASE_URL=http://127.0.0.1:8081
WHISPER_LANGUAGE=en

LLM_BASE_URL=http://127.0.0.1:8080/v1
LLM_MODEL=local

# No GROQ_API_KEY or LLM_API_KEY required for local mode.
```

## Auto-Start Behavior

`run.sh` can start local servers automatically if the URLs point to localhost and the expected binaries and models exist:

```env
LLM_BASE_URL=http://127.0.0.1:8080/v1
LLAMA_SERVER=~/llama.cpp/build/bin/llama-server
LLAMA_MODEL=~/llama.cpp/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf

WHISPER_BASE_URL=http://127.0.0.1:8081
WHISPER_SERVER=~/whisper.cpp/build/bin/whisper-server
WHISPER_MODEL=~/whisper.cpp/models/ggml-large-v3-turbo.bin
WHISPER_LANGUAGE=en
```

If a server is already running on the configured port, `run.sh` leaves it alone.

