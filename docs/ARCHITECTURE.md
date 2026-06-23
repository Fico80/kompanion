# Architecture

## Capabilities

The assistant is split into explicit capability modules. There is no manifest system and no dynamic plugin loader.

```text
backend/capabilities/
├── spotify/     # Spotify search and playback control
├── audio/       # app volume, global audio and media control
├── brightness/  # ddcutil monitor brightness
├── clipboard/   # wl-paste/wl-copy plus text tasks via LLM
├── calendar/    # Google Calendar queries and event creation
├── notes/       # save, search and summarize notes
├── search/      # file search and file deletion
├── shortcuts/   # URL and shortcut sequence management
├── system/      # RAM, CPU, disk, battery and process checks
├── weather/     # weather via wttr.in
├── timer/       # duration based reminders
├── tasks/       # add, query, complete, reopen and delete tasks
├── windows/     # move, close and active-window context
├── browser/     # web search via ddgs, heuristic ranker, auto-open URL
└── screen/      # Wayland screenshot (grim) + vision LLM query
```

`backend/parser.py` imports these parsers directly so command priority stays predictable. `spotify` stays before `audio`, so song requests are not swallowed by generic media control. `system` stays before timer and task parsing, so short queries such as "battery" and "CPU usage" resolve locally. `calendar` stays after clipboard and before weather, so appointment questions are not displaced by general day or today wording. `browser` stays after weather so weather questions are not sent to web search.

## Shared Modules

`backend/shared/paths.py` is the central source for project paths:

`PROJECT_ROOT`, `BACKEND_DIR`, `CONFIG_DIR`, `DATA_DIR`, `STATIC_DIR`, `ENV_FILE`, `APPS_FILE`, `SHORTCUTS_FILE`, `URLS_FILE`, `MEMORY_DB`.

New modules should use these constants instead of rebuilding paths relative to `__file__`.

`backend/shared/llm.py` contains the shared OpenAI-compatible completion helper. It uses `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY`, so the same code can talk to llama.cpp, Ollama or any compatible hosted endpoint.

`backend/shared/config.py` contains shared parser helpers such as app loading and window placement extraction.

`backend/shared/numbers.py` contains `_parse_number()` for converting spoken number words ("five", "fünf") to integers, used by the timer parser.

OAuth routes stay in `backend/main.py`. OAuth clients and token handling live under `backend/auth/`. The calendar capability owns only parsing and execution of calendar actions.

`notes` uses `backend/memory.py` for SQLite, embeddings and similarity search. The capability owns voice parsing, Markdown file creation, backlinks and optional LLM summaries.

`clipboard` wraps the Wayland clipboard tools `wl-paste` and `wl-copy`. It stays after notes and knowledge parsing, so "summarize my notes" does not become a clipboard summary.

`brightness` wraps `ddcutil` and the `DDCUTIL_LEFT_DISPLAY` / `DDCUTIL_RIGHT_DISPLAY` mapping. It stays before `system`, so short commands such as "brighter" remain local and do not need the LLM.

`search` owns file search and file deletion. The interactive selection state for multiple matches remains in `backend/main.py` because it is stateful.

`shortcuts` owns URL and shortcut configuration plus suggestions. `run_shortcut` execution remains in the core executor because it recursively parses and executes commands.

`browser` uses `ddgs` for web search, a 7-signal heuristic ranker to pick the best result, and opens it directly if confidence is above the threshold. Falls back to a DuckDuckGo search page otherwise.

`screen` captures a Wayland screenshot with `grim`, encodes it as base64, and sends it to a vision-capable OpenAI-compatible endpoint (`VISION_BASE_URL`, `VISION_MODEL`).

`backend/executor.py` delegates explicitly by action name to the matching capability executor.

## Interactive State

Before the normal parse and execute pipeline, `backend/main.py` handles stateful checks with TTLs:

- **Undo**: reverses the last reversible action.
- **Yes/No**: asks for confirmation before risky actions.
- **Clarification**: appends missing parameters to the original command and parses it again.
- **Selection**: lets the user choose by ordinal after multiple file search matches.

## Command Logs and Settings API

`backend/memory.py` stores every executed command in the `history` SQLite table via `log_command()`. Three functions expose the log data: `get_logs(limit)`, `delete_log(id)`, `clear_logs()`.

`backend/main.py` exposes:

```
GET    /api/logs           fetch command history
DELETE /api/logs           clear all log entries
DELETE /api/logs/{id}      delete a single entry
GET    /api/settings       read whitelisted .env key-value pairs
POST   /api/settings       write key-value pairs back to .env
```

The settings whitelist in `main.py` (`_SETTINGS_KEYS`) controls which `.env` keys are exposed. The parser/writer handles active lines, commented-out lines and missing keys.

## Web UI

The frontend is served from `static/` and split into:

- `static/js/` — ES modules: `main.js` (entry), `commands.js`, `logs.js`, `settings.js`, `tabs.js`, `api.js`, `templates.js`, `ui.js`, `lib/dom.js`, `lib/storage.js`, `data/quickCommands.js`, `data/cheatSheet.js`
- `static/css/foundation/` — tokens, base, layout, responsive, animations
- `static/css/components/` — one file per UI component

## TTS

`scripts/listener.py` speaks selected actions back to the user using [Piper](https://github.com/rhasspy/piper) for local neural TTS. `espeak-ng` is the fallback when no Piper model is configured.

Actions that trigger TTS: `query_calendar`, `query_weather`, `query_system`, `query_spotify`, `save_note`, `clipboard_task`, `query_shortcut_suggestions`, `save_shortcut_sequence`, `search_files`, `select_item`, `needs_clarification`, `undo`, `close_all_windows`, `confirm`, `add_task`, `query_tasks`, `complete_task`, `query_notes`, `voice_recall`.

## HUD And Session Mode

| State | Color | Meaning |
|---|---|---|
| `listening` | Cyan | Microphone is active |
| `processing` | Blue | Whisper and executor are running |
| `success` | Green | Command succeeded |
| `error` | Red | Command failed |
| `session` | Purple | Waiting for the next command |

All transitions except `session` are event driven. `session` is set by the one-second `_session_poll` timer.

Wake-word mode transitions:

- Normal command: green for 2 seconds, then purple "Ready..."
- TTS command: green stays visible while TTS runs, then purple after TTS finishes
- Error: red for 2 seconds, then purple so the user can retry
- Session timeout: the HUD fades out and media resumes

`_result_shown_at` is `None` while TTS is running and `time.time()` otherwise. The poll checks for a delay greater than 2 seconds.

## KWin And Wayland

- New windows: KWin JavaScript over D-Bus with a `windowAdded` listener, geometry retries at 300, 800 and 1400 ms and a 15 second timeout.
- Window moves: iterate through all virtual desktops because `stackingOrder` only covers the current desktop.
- Wayland apps such as Firefox, VS Code and Spotify: `xdotool` is not reliable, so window control uses KWin D-Bus.
- Orb HUD: runs through XWayland with `QT_QPA_PLATFORM=xcb`.

## Local Voice Commands

Some voice commands are handled locally in `scripts/listener.py` and never reach the backend or LLM:

- **Sleep**: ends the active wake-word session.
- **Wait**: keeps the session open for a moment.
- **Recall**: repeats the last heard transcript.
- **Safe repeat**: repeats only safe relative volume and brightness commands.

## Media Pause

`MediaPauseManager` pauses active MPRIS players when recording starts and resumes only the players it paused itself. If the user explicitly controls playback, the remembered pause state is discarded.

## Window Context

After window actions, the listener remembers the last app or window. Pronoun commands such as "move it left" or "close it" are expanded locally. "Move it back" uses a remembered inverse command where possible, with KWin restore as a fallback.
