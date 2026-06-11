# Kompanion

A local-first desktop assistant for KDE Plasma 6 on Wayland. Control your desktop through voice commands or a small web UI. Core workflows can run fully offline.

English and German are supported for the main workflows.

## Features

Most features work without an LLM through deterministic local parsers. Features marked with ⚡ use an LLM when configured but degrade gracefully without one.

**Windows and apps**
- Open apps, folders and URLs by voice
- Place new windows left, right, fullscreen, on a specific workspace or monitor
- Move and close existing windows through KWin D-Bus
- Follow-up window commands: "move it right", "send it back", "close it again"
- Open multiple apps in one command: "open Firefox left and Discord right"
- ⚡ Unknown apps and URLs are resolved via LLM fallback

**Audio and media**
- Control system volume, per-app volume and media playback
- Control Spotify through the Spotify Web API

**Notes**
- Dictate Markdown notes saved to `~/Notes`
- Append to existing notes by voice
- ⚡ Note formatting and smart filenames (requires LLM)
- ⚡ Search and summarize saved notes (requires LLM; falls back to substring search)
- Link similar notes automatically for Obsidian-style graph workflows

**Tasks and calendar**
- Create timers, tasks and reminders with due dates
- ⚡ Query Google Calendar and create events by voice (requires LLM for natural language dates)

**System**
- Adjust monitor brightness through `ddcutil` and DDC/CI
- Search files and folders by name, type and time range
- Ask for system information: RAM, CPU, disk, battery, top processes
- Query weather through `wttr.in`

**Clipboard**
- ⚡ Translate, summarize, explain or improve clipboard text (requires LLM)

**Configuration and shortcuts**
- Configure LLM, STT, TTS and integrations through the web UI Settings tab
- Save custom URL aliases and command shortcuts without restarting
- Push-to-talk with the right Ctrl key
- Optional wake word mode with openWakeWord, VAD and a small PyQt HUD
- Fully local AI stack: [Piper](https://github.com/rhasspy/piper) for TTS, `whisper.cpp` or Ollama for STT, Ollama or `llama.cpp` for LLM

## Requirements

Python 3.10 or newer is required.

Install the system dependencies on Fedora:

```bash
sudo dnf install playerctl pipewire-utils qt6-qttools ddcutil ffmpeg espeak-ng lsof wl-clipboard libnotify
```

`ffmpeg` includes `ffplay` which is used for TTS audio playback. On Fedora it requires [RPM Fusion](https://rpmfusion.org/).

For push-to-talk hotkeys:

```bash
sudo usermod -aG input $USER
```

For monitor brightness through `ddcutil`:

```bash
sudo usermod -aG i2c $USER
```

Log out and back in after changing groups.

### Text-to-Speech

TTS uses [Piper](https://github.com/rhasspy/piper) for local neural speech. `espeak-ng` is the fallback when no Piper model is configured.

Download voice models from [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/main). You need the `.onnx` file and the `.onnx.json` config file in the same folder.

Example Piper models:

| Language | Model |
|---|---|
| English | `en_US-lessac-medium` |
| German | `de_DE-thorsten-medium` |

```bash
mkdir -p ~/.local/share/piper
# English
wget -P ~/.local/share/piper \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx" \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json"
# German
wget -P ~/.local/share/piper \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx" \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx.json"
```

Then set in `.env`:

```env
PIPER_MODEL_EN=~/.local/share/piper/en_US-lessac-medium.onnx
PIPER_MODEL_DE=~/.local/share/piper/de_DE-thorsten-medium.onnx
```

### Speech-to-Text

Run [whisper.cpp](https://github.com/ggml-org/whisper.cpp) locally, no API key needed. See [Local AI Setup](#local-ai-setup) for the setup command. 

If you prefer a cloud provider, set `STT_BASE_URL` and `STT_API_KEY` in `.env`.

### Wake Word

To enable always-on wake word mode, set in `.env`:

```env
WAKE_WORD_ENABLED=1
```

All tuning options are documented in `.env.example`.

## Quick Start

Clone the project and create a config file:

```bash
cp .env.example .env
```

Edit `.env` for your setup. Then start the assistant:

```bash
./run.sh
```

The script will:

- create a Python virtual environment if needed
- install Python dependencies
- start the FastAPI backend on `http://127.0.0.1:8000`
- start the voice listener
- start the reminder daemon
- optionally start local `llama-server` or `whisper-server` if configured

Open the web UI:

```text
http://127.0.0.1:8000
```

The web UI has three tabs: **Commands** (quick tiles, suggestions, cheat sheet), **Logs** (full command history with filtering and delete), and **Settings** (configure LLM, STT, TTS, HUD, integrations and more without editing `.env` manually).

## Configuration

Copy `.env.example` to `.env` to get started. The **Settings tab** in the web UI covers the most common options (LLM, STT, TTS, HUD, integrations) without having to edit the file manually. Advanced options are documented inline in `.env.example`.

For Spotify and Google Calendar, OAuth setup is required. Add the following redirect URIs to your developer app:

```text
http://127.0.0.1:8000/spotify/callback
http://127.0.0.1:8000/calendar/callback
```

Then authorize once in the browser at `http://127.0.0.1:8000/spotify/auth` or `/calendar/auth`.

## Local AI Setup

The assistant is designed to run fully local. One known-working stack is Ollama for LLM and embeddings, `whisper.cpp` for STT, and Piper for TTS.

### Ollama

Install [Ollama](https://ollama.com), then pull the models you need:

```bash
ollama pull qwen2.5:7b          # LLM
ollama pull nomic-embed-text    # embeddings for note search
```

Then set:

```env
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_MODEL=qwen2.5:7b
EMBED_BASE_URL=http://127.0.0.1:11434/v1
EMBED_MODEL=nomic-embed-text
```

### llama.cpp

```bash
LLAMA_SERVER=~/llama.cpp/build/bin/llama-server \
LLAMA_MODEL=~/llama.cpp/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
./scripts/start_llama.sh
```

Then set:

```env
LLM_BASE_URL=http://127.0.0.1:8080/v1
LLM_MODEL=local
```

### whisper.cpp

```bash
~/whisper.cpp/build/bin/whisper-server \
  -m ~/whisper.cpp/models/ggml-large-v3-turbo.bin \
  -l en \
  --host 127.0.0.1 \
  --port 8081
```

Then set:

```env
WHISPER_BASE_URL=http://127.0.0.1:8081
WHISPER_LANGUAGE=en
```

More details are in `docs/LOCAL_AI.md`.

## Example Commands

```text
open Firefox left
öffne Firefox links
open Firefox left and Discord right
move it back
volume 50
play playlist Chill
create event dentist tomorrow at 3 pm
remind me tomorrow to pay the bill
summarize this
find the PDF from last week
```

See `docs/COMMANDS.md` for a longer command list.

## Custom Apps, URLs and Shortcuts

User-editable configuration lives in `config/`.

```text
config/apps.json        app commands, window classes and titles
config/apps.local.json  optional private app overrides, ignored by Git
config/urls.json        custom URL aliases
config/shortcuts.json   reusable command sequences
```

Use `config/apps.local.json` for machine-specific commands such as AppImage paths.
Entries in `apps.local.json` override or extend `apps.json`.

Changes to URL aliases and shortcuts are picked up without restarting.

Example shortcut idea:

```text
open VS Code left
open Firefox right
open Discord
```

Then trigger it with a custom command such as:

```text
start work mode
```

## API

Execute a command:

```http
POST /api/execute
Content-Type: application/json

{"command": "open Firefox left"}
```

Logs endpoints:

```text
GET    /api/logs
DELETE /api/logs
DELETE /api/logs/{id}
```

Settings endpoints:

```text
GET  /api/settings
POST /api/settings
```

Memory endpoints:

```text
GET /api/memory/recent
GET /api/memory/top
GET /api/memory/stats
GET /api/memory/notes
GET /api/memory/suggestions
```

Auth endpoints:

```text
GET /spotify/auth
GET /calendar/auth
```

## Documentation

Additional docs:

- `docs/COMMANDS.md` for a longer list of supported command examples.
- `docs/LOCAL_AI.md` for local `whisper.cpp` and `llama.cpp` setup.
- `.env.example` for all environment variables with inline documentation.
- `docs/ARCHITECTURE.md` for capability layout, parser order and runtime state.
- `docs/LANGUAGES.md` for the planned language-pack structure and how to add a language.
- `SECURITY.md` for release and local API security notes.

## Development

Run tests:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

Compile-check the main Python files:

```bash
python3 -m py_compile \
  backend/parser.py \
  backend/executor.py \
  backend/main.py \
  backend/capabilities/*/parser.py \
  backend/capabilities/*/executor.py \
  scripts/listener.py
```

For manual parser checks, use examples from `docs/COMMANDS.md`.

## Contributing

Bug reports and feature requests are welcome. Open an issue or start a discussion on GitHub.

## Notes and Limitations

- The assistant is tailored to KDE Plasma 6 and Wayland.
- Window control depends on KWin D-Bus and `qdbus-qt6`.
- Brightness control depends on monitor DDC/CI support and `ddcutil`.
- Spotify and Google Calendar require OAuth setup.
- English and German are supported. See `docs/LANGUAGES.md` for adding more languages.
