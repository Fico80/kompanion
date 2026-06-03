# Kompanion

A local-first desktop assistant for KDE Plasma 6 on Wayland. It can control windows, open apps and URLs, search files, manage notes, create calendar events, control audio, adjust monitor brightness, run timers and answer system questions through voice commands or a small web UI.

The project is designed for Linux desktop automation rather than general chatbot use. Most commands are handled by deterministic local parsers. An OpenAI-compatible LLM endpoint is only used as a fallback or for text tasks such as summaries, explanations and note queries.

## Current Status

This is a working personal assistant that is being cleaned up for broader use. The main target is currently:

- Fedora Linux
- KDE Plasma 6
- Wayland
- KWin window management through D-Bus

English and German commands are supported for the main workflows. Responses are generated in the detected command language for the most important user-facing actions.

## Features

- Open apps, folders and URLs by voice.
- Place new windows left, right, fullscreen, on a specific workspace or on a specific monitor.
- Move and close existing windows through KWin D-Bus.
- Understand follow-up window commands such as "move it right", "send it back" and "close it again".
- Open multiple apps in one command, for example "open Firefox left and Discord right".
- Control system volume, per-app volume and media playback.
- Control Spotify through the Spotify Web API.
- Adjust monitor brightness through `ddcutil` and DDC/CI.
- Search files and folders by name, type and time range.
- Dictate Markdown notes into `~/Notes`.
- Search and summarize saved notes.
- Link similar notes automatically for Obsidian-style graph workflows.
- Query Google Calendar and create events by voice.
- Create timers, tasks and reminders.
- Ask for system information such as RAM, CPU, disk, battery and top processes.
- Query weather through `wttr.in`.
- Save custom URL aliases and command shortcuts without restarting.
- Use push-to-talk with the right Ctrl key.
- Optional wake word mode with openWakeWord, VAD and a small PyQt HUD.
- Fully local AI stack: Piper for TTS, `whisper.cpp` or Ollama Whisper for STT, Ollama or `llama.cpp` for LLM, Ollama embeddings for note search.

## Architecture

The assistant is built around a staged intent pipeline:

```text
voice or web input
-> parser pipeline
-> capability executor
-> desktop action or API call
-> optional spoken response
```

Core modules:

```text
backend/main.py              FastAPI server and interactive state
backend/parser.py            ordered intent pipeline
backend/executor.py          action dispatcher
backend/kwin_client.py       KWin Wayland window control
backend/memory.py            SQLite history, tasks and notes
backend/shared/              shared paths, config, i18n and LLM helpers
backend/capabilities/        feature-specific parsers and executors
scripts/listener.py          hotkey, wake word, STT, TTS and HUD
static/                      small web UI
config/                      user-editable app, URL and shortcut config
```

Capabilities are explicit Python modules rather than a dynamic plugin system:

```text
audio, brightness, calendar, clipboard, notes, search, shortcuts,
spotify, system, tasks, timer, weather, windows
```

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

Download voice models from [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/main) — you need the `.onnx` file and the `.onnx.json` config file in the same folder.

Recommended models:

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

## Configuration

Copy `.env.example` to `.env` and configure only what you need.

### Speech-to-Text

Cloud option with Groq:

```env
GROQ_API_KEY=<your-groq-api-key>
WHISPER_LANGUAGE=en
```

Generic STT provider:

```env
STT_API_KEY=<your-stt-api-key>
STT_MODEL=whisper-large-v3-turbo
```

Local `whisper.cpp` server:

```env
WHISPER_BASE_URL=http://127.0.0.1:8081
WHISPER_LANGUAGE=en
```

If `WHISPER_BASE_URL` points to localhost, the listener calls the `whisper.cpp` `/inference` endpoint. For remote STT providers it uses an OpenAI-style transcription endpoint.

### LLM

The assistant talks to OpenAI-compatible chat completion endpoints.

Local `llama.cpp`:

```env
LLM_BASE_URL=http://127.0.0.1:8080/v1
LLM_MODEL=local
```

Ollama:

```env
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_MODEL=qwen2.5:7b
```

Cloud provider:

```env
LLM_API_KEY=<your-llm-api-key>
LLM_BASE_URL=https://provider.example.com/v1
LLM_MODEL=provider-model-name
```

If `/chat/completions` is missing from `LLM_BASE_URL`, the code appends it automatically.

### Spotify

Create a Spotify developer app and add this redirect URI:

```text
http://127.0.0.1:8000/spotify/callback
```

Then set:

```env
SPOTIFY_CLIENT_ID=<your-spotify-client-id>
SPOTIFY_CLIENT_SECRET=<your-spotify-client-secret>
```

Connect once in the browser:

```text
http://127.0.0.1:8000/spotify/auth
```

### Google Calendar

Create a Google OAuth app and add this redirect URI:

```text
http://127.0.0.1:8000/calendar/callback
```

Then set:

```env
GOOGLE_CLIENT_ID=<your-google-client-id>
GOOGLE_CLIENT_SECRET=<your-google-client-secret>
```

Connect once in the browser:

```text
http://127.0.0.1:8000/calendar/auth
```

### Wake Word

Enable always-on wake word mode:

```env
WAKE_WORD_ENABLED=1
WAKE_WORD=hey_jarvis_v0.1
WAKE_WORD_THRESHOLD=0.60
WAKE_CONSECUTIVE_BLOCKS=2
WAKE_REQUIRE_VAD=1
WAKE_SESSION_TIMEOUT=15
WAKE_LOCAL_WAIT_SECONDS=30
VOICE_PAUSE_MEDIA_ON_TRIGGER=1
VOICE_RESUME_MEDIA_ON_SLEEP=1
```

With wake word disabled, use the right Ctrl key as push-to-talk.

### Embeddings

Embeddings enable semantic note search. Without them, note search falls back to substring matching.

```env
EMBED_BASE_URL=http://127.0.0.1:11434/v1
EMBED_MODEL=nomic-embed-text
```

Any OpenAI-compatible embeddings endpoint works. For cloud providers, set `EMBED_API_KEY` (falls back to `LLM_API_KEY` if not set).

## Local AI Setup

The assistant is designed to run fully local. The recommended stack is Ollama for LLM and embeddings, `whisper.cpp` for STT, and Piper for TTS.

### Ollama (recommended)

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

### Apps and Windows

```text
open Firefox
open Firefox left
open Firefox on workspace 2
open Firefox left and Discord right
move Firefox to the right
move the active window to workspace 3
move it back
close Firefox
close all windows
```

German examples:

```text
öffne Firefox links
verschiebe Firefox auf Arbeitsfläche 2
mach es rechts
schiebe es zurück
schließe alle Fenster
```

### Audio and Media

```text
volume 50
volume up
volume down
mute
unmute
Spotify quieter
next song
pause music
play music
```

### Spotify

```text
play playlist Chill
play the song Around the World by Daft Punk
what is playing
```

### Calendar

```text
what do I have today
what do I have tomorrow
show my events this week
create event dentist tomorrow at 3 pm
schedule meeting next Monday at 10:30 am
```

### Tasks and Timers

```text
remind me tomorrow to pay the bill
add task submit documents
show my tasks
mark task 2 as done
timer 10 minutes
remind me in 30 minutes to call back
```

### Notes and Clipboard

```text
note: idea for a KDE assistant feature
what did I note about Project Phoenix
summarize my notes from last week
translate this
summarize this
explain this
improve this text
```

### Files and System

```text
find the PDF from last week
open folder downloads
open file invoice May
how much RAM am I using
system status
how is the weather
```

### Local Voice Session Commands

```text
stop listening
wait a moment
what did you hear
do that again
```

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

- `docs/LOCAL_AI.md` for local `whisper.cpp` and `llama.cpp` setup.
- `.env.example` for all environment variables with inline documentation.
- `docs/ARCHITECTURE.md` for capability layout, parser order and runtime state.
- `docs/LANGUAGES.md` for the planned language-pack structure and how to add a language.
- `SECURITY.md` for release and local API security notes.

## Development

Run tests:

```bash
python3 -m unittest tests/test_parser.py tests/test_features.py
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

Useful manual checks after parser or capability changes:

```text
open Firefox right
open Firefox left and Discord right
move it back
close all windows
volume 30
Spotify quieter
create event dentist tomorrow at 3 pm
remind me tomorrow to pay the bill
show my tasks
what is my RAM usage
```

## Notes and Limitations

- The assistant is tailored to KDE Plasma 6 and Wayland.
- Window control depends on KWin D-Bus and `qdbus-qt6`.
- Brightness control depends on monitor DDC/CI support and `ddcutil`.
- Spotify and Google Calendar require OAuth setup.
- English and German are supported. See `docs/LANGUAGES.md` for adding more languages.
