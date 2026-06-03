import sys
import os
import re
import time
import html
import threading
import subprocess
import argparse
import uvicorn

# Ensure the backend directory is in the import path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from shared.paths import ENV_FILE, STATIC_DIR, MEMORY_DB, DATA_DIR


def _secure_sensitive_files() -> None:
    """Chmod sensitive files and directories to owner-only if they are world-readable."""
    from pathlib import Path
    import stat

    # Files that must be 0o600
    files_600 = [
        ENV_FILE,
        MEMORY_DB,
        Path(os.path.expanduser("~/.config/kompanion/spotify_tokens.json")),
        Path(os.path.expanduser("~/.config/kompanion/google_calendar_tokens.json")),
    ]
    # Directories that must be 0o700
    dirs_700 = [
        DATA_DIR,
        Path(os.path.expanduser("~/.config/kompanion")),
    ]

    for path in files_600:
        if path.exists():
            try:
                if stat.S_IMODE(path.stat().st_mode) & 0o077:
                    path.chmod(0o600)
            except OSError:
                pass

    for path in dirs_700:
        if path.exists():
            try:
                if stat.S_IMODE(path.stat().st_mode) & 0o077:
                    path.chmod(0o700)
            except OSError:
                pass


def _load_env():
    if not ENV_FILE.exists():
        return
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

_load_env()
_secure_sensitive_files()

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel
from parser import parse_command
from executor import execute_parsed_intent
from shared.i18n import detect_language, lang
import auth.spotify as sp_auth
import auth.google_calendar as gc_auth
import memory as mem

# Pydantic schema for API requests
class CommandRequest(BaseModel):
    command: str

app = FastAPI(
    title="Local Assistant API",
    description="Backend API for local desktop window assistant"
)
mem.init_db()


def _cors_origins() -> list[str]:
    configured = os.environ.get("ASSISTANT_CORS_ORIGINS", "").strip()
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return [
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ]

# --- Stage 0: pending interaction state ---
# All four globals are protected by _state_lock.
# FastAPI runs synchronous endpoints in a thread pool, so concurrent requests
# would otherwise corrupt session state without this lock.

_state_lock = threading.Lock()

_pending_selection: dict | None = None
_SELECTION_TTL = 30  # seconds

_pending_confirmation: dict | None = None
_CONFIRMATION_TTL = 45  # seconds, more time to formulate a date or destination

_last_undo: dict | None = None
_UNDO_RE = re.compile(r"\b(rückgängig|undo|zurücknehmen|das\s+zurück|revert)\b")

# Yes/No confirmation for risky actions (e.g. "schließe alles")
_pending_yesno: dict | None = None
_YESNO_TTL = 45  # seconds
_YES_RE = re.compile(
    r"\b(ja|jo|jou|jup|jep|yes|yep|klar|sicher|bestätigen?|bestätige|jawohl|"
    r"okay|ok|definitiv|auf\s+jeden\s+fall|mach\s+(?:es|schon|ruhig|weiter))\b"
)
_NO_RE = re.compile(
    r"\b(nein|nö|nee|nope|no|abbrechen|abbruch|cancel|doch\s+nicht|"
    r"lass\s+(?:es|mal)|vergiss(?:\s+es)?|stopp?)\b"
)

def _build_undo(parsed: dict, result: dict) -> dict | None:
    """Return an undo-parseable dict for the given action, or None if not reversible."""
    action = parsed.get("action")
    _l = lang(parsed)
    _null = {"window_title": None, "window_class": None, "flatpak_id": None,
             "layout": None, "desktop": None, "monitor": None}

    if action == "close_app":
        cmd = parsed.get("app_cmd")
        if cmd:
            return {"action": "open_app", "target": cmd, "app_name": parsed.get("app_name", ""),
                    "window_class": parsed.get("window_class", ""),
                    "window_title": parsed.get("window_title", ""), **_null}

    elif action == "open_app":
        return {"action": "close_app", "target": parsed.get("window_class"),
                "app_name": parsed.get("app_name", ""),
                "window_class": parsed.get("window_class", ""),
                "window_title": parsed.get("window_title", ""), **_null}

    elif action == "save_note":
        path = (result.get("details") or {}).get("path")
        if path:
            return {"action": "delete_file", "target": path,
                    "app_name": "Notiz gelöscht" if _l == "de" else "Note deleted", **_null}

    elif action == "save_url":
        return {"action": "delete_url", "target": parsed.get("target"),
                "app_name": "URL entfernt" if _l == "de" else "URL removed", **_null}

    elif action == "save_shortcut_desc":
        return {"action": "delete_shortcut", "target": parsed.get("target"),
                "app_name": "Shortcut entfernt" if _l == "de" else "Shortcut removed", **_null}

    elif action == "delete_shortcut":
        cmds = result.get("original_commands")
        if cmds:
            return {"action": "save_shortcut_desc", "target": parsed.get("target"),
                    "shortcut_commands": cmds,
                    "app_name": "Shortcut wiederhergestellt" if _l == "de" else "Shortcut restored", **_null}

    elif action == "add_task":
        task_id = result.get("task_id")
        if task_id is not None:
            return {"action": "delete_task", "target": task_id,
                    "app_name": "Aufgabe entfernt" if _l == "de" else "Task removed", **_null}

    elif action == "complete_task":
        task_id = result.get("task_id")
        if task_id is not None:
            return {"action": "reopen_task", "target": task_id,
                    "app_name": "Aufgabe wieder offen" if _l == "de" else "Task reopened", **_null}

    elif action == "set_volume":
        t = parsed.get("target", "")
        if t == "mute":         undo_t = "unmute"
        elif t == "unmute":     undo_t = "mute"
        elif t.startswith("+"): undo_t = "-" + t[1:]
        elif t.startswith("-"): undo_t = "+" + t[1:]
        else:                   undo_t = result.get("prev_volume")
        if undo_t:
            return {"action": "set_volume", "target": undo_t,
                    "app_name": "Lautstärke zurück" if _l == "de" else "Volume restored", **_null}

    elif action == "set_brightness":
        t = parsed.get("target", "")
        if t.startswith("+"):   undo_t = "-" + t[1:]
        elif t.startswith("-"): undo_t = "+" + t[1:]
        else:                   undo_t = None
        if undo_t:
            return {"action": "set_brightness", "target": undo_t,
                    "monitor": parsed.get("monitor"),
                    "app_name": "Helligkeit zurück" if _l == "de" else "Brightness restored", **_null}

    return None

def _resolve_selection(text_lower: str, count: int) -> int | None:
    """Returns 0-based index if text is a file selection, -1 if cancel, None if not a selection."""
    if re.search(r"\b(keine[ns]?|none|abbrechen|abbruch|cancel|nein|no)\b", text_lower):
        return -1
    # Strip filler words. After stripping, the entire remainder must be just an ordinal or number.
    s = re.sub(r"\b(die|den|das|bitte|öffnen?|nimm|zeige?|mir|option|datei|nummer|the|please|open|take|show|me|file|number)\b", "", text_lower)
    s = re.sub(r"\s+", " ", s).strip()
    for pattern, idx in [
        (r"erste[nrs]?|eins?|first|one|1", 0),
        (r"zweite[nrs]?|zwei|second|two|2", 1),
        (r"dritte[nrs]?|drei|third|three|3", 2),
        (r"vierte[nrs]?|vier|fourth|four|4", 3),
        (r"fünfte[nrs]?|fünf|fifth|five|5", 4),
    ]:
        if idx < count and re.fullmatch(pattern, s):
            return idx
    return None

# Enable CORS only for the local frontend by default. The API can open apps,
# files and windows, so broad browser access would be risky.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/execute")
def execute_command(req: CommandRequest):
    """Parses and executes a natural language command."""
    with _state_lock:
        return _execute_command_locked(req)


def _execute_command_locked(req: CommandRequest):
    global _pending_selection, _pending_confirmation, _last_undo, _pending_yesno
    request_lang = detect_language(req.command)

    now = time.time()
    if _pending_selection and now > _pending_selection["expires_at"]:
        _pending_selection = None
    if _pending_confirmation and now > _pending_confirmation["expires_at"]:
        _pending_confirmation = None
    if _pending_yesno and now > _pending_yesno["expires_at"]:
        _pending_yesno = None

    # Stage 0: undo always takes priority over everything else.
    if _UNDO_RE.search(req.command.lower()):
        if _last_undo:
            undo_desc = _last_undo.get("description", "")
            undo_parsed = _last_undo["undo_parsed"]
            undo_parsed["lang"] = request_lang
            _last_undo = None
            _pending_confirmation = None
            _pending_selection = None
            result = execute_parsed_intent(undo_parsed)
            if result.get("success") and undo_desc:
                result["message"] = (
                    f"Rückgängig '{undo_desc}'. {result['message']}"
                    if request_lang == "de"
                    else f"Undid '{undo_desc}'. {result['message']}"
                )
        else:
            result = {"success": False, "message": "Nichts zum Rückgängig machen." if request_lang == "de" else "Nothing to undo."}
        parsed = {"action": "undo", "_stage": "undo", "app_name": "Rückgängig" if request_lang == "de" else "Undo", "lang": request_lang}
        print(f"[UNDO] \"{req.command}\" -> {result['message']}")
        mem.log_command(req.command, parsed, result.get("success", False))
        return {"command": req.command, "parsed": parsed, "result": result}

    # Stage 0c: resolve pending yes/no confirmation for a risky action
    if _pending_yesno:
        cmd_l = req.command.lower().strip()
        pending_lang = lang(_pending_yesno.get("parsed"))
        if _NO_RE.search(cmd_l):
            _pending_yesno = None
            result = {"success": True, "message": "Abgebrochen." if pending_lang == "de" else "Cancelled."}
            parsed = {"action": "confirm", "target": "no", "_stage": "confirm", "app_name": "Abgebrochen" if pending_lang == "de" else "Cancelled", "lang": pending_lang}
            print(f"[CONFIRM] \"{req.command}\" -> cancelled")
            mem.log_command(req.command, parsed, True)
            return {"command": req.command, "parsed": parsed, "result": result}
        if _YES_RE.search(cmd_l):
            pend = _pending_yesno["parsed"]
            _pending_yesno = None
            result = execute_parsed_intent(pend)
            if result.get("success"):
                undo = _build_undo(pend, result)
                if undo:
                    undo.setdefault("lang", lang(pend))
                    _last_undo = {"description": pend.get("app_name", pend.get("action")), "undo_parsed": undo}
            parsed = {**pend, "_stage": "confirm"}
            print(f"[CONFIRM] \"{req.command}\" -> confirmed: {pend.get('action')}")
            mem.log_command(req.command, parsed, result.get("success", False))
            return {"command": req.command, "parsed": parsed, "result": result}
        # Neither yes nor no — keep pending and process as a fresh command.
        # _pending_yesno is cleared below only if the command succeeds.

    # Stage 0b: resolve pending command clarification (append missing parameters)
    if _pending_confirmation:
        pending_lang = _pending_confirmation.get("lang", request_lang)
        if time.time() > _pending_confirmation["expires_at"]:
            _pending_confirmation = None
        elif re.search(r"\b(abbrechen|abbruch|cancel|nein|vergiss)\b", req.command.lower()):
            _pending_confirmation = None
            result = {"success": True, "message": "Abgebrochen." if pending_lang == "de" else "Cancelled."}
            parsed = {"action": "select_item", "target": -1, "_stage": "selection", "lang": pending_lang}
            mem.log_command(req.command, parsed, True)
            return {"command": req.command, "parsed": parsed, "result": result}
        else:
            original = _pending_confirmation["original_command"]
            merged = f"{original} {req.command}"
            _pending_confirmation = None
            parsed = parse_command(merged)
            print(f"[{parsed.get('_stage','?').upper()}+CLARIFY] \"{merged}\" -> {parsed.get('action','?')}")
            if parsed.get("action") == "needs_clarification":
                result = {"success": False, "message": "Nicht erkannt. Bitte konkreter angeben." if lang(parsed) == "de" else "Not recognized. Please be more specific."}
            else:
                result = execute_parsed_intent(parsed)
            mem.log_command(req.command, parsed, result.get("success", False))
            return {"command": req.command, "parsed": parsed, "result": result}

    # Stage 0a: resolve pending file selection before normal pipeline
    if _pending_selection:
        files = _pending_selection["files"]
        pending_lang = _pending_selection.get("lang", request_lang)
        sel = _resolve_selection(req.command.lower().strip(), len(files))
        if sel is not None:
            _pending_selection = None
            if sel == -1:
                result = {"success": True, "message": "Abgebrochen." if pending_lang == "de" else "Cancelled."}
            else:
                path = files[sel]
                name = os.path.basename(path)
                if os.path.isdir(path):
                    subprocess.Popen(["dolphin", "--new-window", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                result = {"success": True, "message": f"Öffne {name}" if pending_lang == "de" else f"Opening {name}"}
            parsed = {"action": "select_item", "target": sel, "_stage": "selection", "lang": pending_lang}
            print(f"[SELECTION] \"{req.command}\" -> {sel} ({result['message']})")
            mem.log_command(req.command, parsed, result["success"])
            return {"command": req.command, "parsed": parsed, "result": result}

    # Normal pipeline
    parsed = parse_command(req.command)
    stage = parsed.get("_stage", "?")
    action = parsed.get("action", "?")
    print(f"[{stage.upper()}] \"{req.command}\" -> {action}")

    # Intercept needs_clarification and ask before executing.
    if action == "needs_clarification":
        _pending_confirmation = {
            "original_command": parsed.get("original_command", req.command),
            "lang": lang(parsed),
            "expires_at": time.time() + _CONFIRMATION_TTL,
        }
        result = {"success": True, "message": parsed.get("prompt", "Bitte präzisieren." if lang(parsed) == "de" else "Please clarify.")}
        mem.log_command(req.command, parsed, True)
        return {"command": req.command, "parsed": parsed, "result": result}

    # Intercept risky actions and ask for yes/no before executing.
    if parsed.get("requires_confirmation"):
        _pending_yesno = {
            "parsed": {k: v for k, v in parsed.items()
                       if k not in ("requires_confirmation", "confirm_prompt")},
            "lang": lang(parsed),
            "expires_at": time.time() + _YESNO_TTL,
        }
        _pending_confirmation = None
        _pending_selection = None
        result = {"success": True, "message": parsed.get("confirm_prompt", "Bist du sicher? Sag ja oder nein." if lang(parsed) == "de" else "Are you sure? Say yes or no.")}
        mem.log_command(req.command, parsed, True)
        return {"command": req.command, "parsed": parsed, "result": result}

    result = execute_parsed_intent(parsed)

    # Store undo record for reversible actions
    if result.get("success"):
        undo = _build_undo(parsed, result)
        if undo:
            undo.setdefault("lang", lang(parsed))
            _last_undo = {"description": parsed.get("app_name", action), "undo_parsed": undo}

    # Clear yes/no state after any successful command
    if result.get("success") and _pending_yesno:
        _pending_yesno = None

    # After append_note: ask if user wants to open the note
    if result.get("_open_on_yes"):
        _pending_yesno = {
            "parsed": {
                "action": "open_path",
                "target": result["_open_on_yes"],
                "layout": None, "desktop": None, "monitor": None,
                "lang": lang(parsed),
            },
            "lang": lang(parsed),
            "expires_at": time.time() + _YESNO_TTL,
        }

    # Store pending selection if executor returned one
    if result.get("pending_selection"):
        _pending_selection = {
            "files": result["pending_selection"],
            "lang": lang(parsed),
            "expires_at": time.time() + _SELECTION_TTL,
        }

    mem.log_command(req.command, parsed, result.get("success", False))
    return {
        "command": req.command,
        "parsed": parsed,
        "result": result
    }

@app.get("/api/memory/recent")
def memory_recent():
    return mem.get_recent(20)

@app.get("/api/memory/top")
def memory_top():
    return mem.get_top_commands(10)

@app.get("/api/memory/stats")
def memory_stats():
    return mem.get_stats()

@app.get("/api/memory/notes")
def memory_notes():
    return mem.get_notes(20)

@app.get("/api/memory/suggestions")
def memory_suggestions():
    return mem.get_suggestions()

@app.post("/api/kwin_debug")
async def kwin_debug(request: Request):
    body = await request.json()
    print(f"[KWin-Debug] {body.get('data', '')}")
    return {"ok": True}

@app.get("/spotify/auth")
def spotify_login():
    return RedirectResponse(url=sp_auth.get_auth_url())

@app.get("/spotify/callback")
def spotify_callback(code: str = None, error: str = None, state: str = None):
    if error:
        return HTMLResponse(f"<h1>Error: {html.escape(error)}</h1>")
    if not code:
        return HTMLResponse("<h1>No code received.</h1>")
    if not sp_auth.verify_state(state or ""):
        return HTMLResponse("<h1 style='color:red'>Invalid state — possible CSRF attempt. Please try logging in again.</h1>", status_code=400)
    try:
        sp_auth.exchange_code(code)
        return HTMLResponse("<h1 style='font-family:sans-serif;color:green'>✅ Spotify connected! You can close this window.</h1>")
    except Exception as e:
        return HTMLResponse(f"<h1 style='color:red'>Error: {html.escape(str(e))}</h1>")

@app.get("/spotify/status")
def spotify_status():
    return {"authenticated": sp_auth.is_authenticated()}


@app.get("/calendar/auth")
def calendar_login():
    return RedirectResponse(url=gc_auth.get_auth_url())

@app.get("/calendar/callback")
def calendar_callback(code: str = None, error: str = None, state: str = None):
    if error:
        return HTMLResponse(f"<h1>Error: {html.escape(error)}</h1>")
    if not code:
        return HTMLResponse("<h1>No code received.</h1>")
    if not gc_auth.verify_state(state or ""):
        return HTMLResponse("<h1 style='color:red'>Invalid state — possible CSRF attempt. Please try logging in again.</h1>", status_code=400)
    try:
        gc_auth.exchange_code(code)
        return HTMLResponse("<h1 style='font-family:sans-serif;color:green'>✅ Google Calendar connected! You can close this window.</h1>")
    except Exception as e:
        return HTMLResponse(f"<h1 style='color:red'>Error: {html.escape(str(e))}</h1>")

@app.get("/calendar/status")
def calendar_status():
    return {"authenticated": gc_auth.is_authenticated()}


STATIC_DIR.mkdir(exist_ok=True)

# Mount the static files directory to serve the frontend
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

def main():
    parser = argparse.ArgumentParser(description="Local desktop assistant for custom window management.")
    parser.add_argument("--cli", type=str, help="Execute a single command directly in CLI mode and exit")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the FastAPI web server on")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface to bind the FastAPI web server to")
    
    args = parser.parse_args()
    
    if args.cli:
        print(f"--- CLI Mode: Executing '{args.cli}' ---")
        parsed = parse_command(args.cli)
        print(f"Parsed Intent:")
        for k, v in parsed.items():
            print(f"  {k}: {v}")
        print("-" * 40)
        result = execute_parsed_intent(parsed)
        print(f"Execution Result: {'Success' if result['success'] else 'Failed'}")
        print(f"  Message: {result['message']}")
        if 'details' in result:
            print(f"  Details: {result['details']}")
        sys.exit(0 if result["success"] else 1)
        
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(
            "Warning: binding the assistant API outside localhost exposes desktop-control endpoints. "
            "Only do this on a trusted network."
        )
    print(f"Starting Assistant Server at http://{args.host}:{args.port}")
    # Run uvicorn server. Since uvicorn.run blocks, we set reload=True only if running from this file directly
    uvicorn.run("main:app", host=args.host, port=args.port)

if __name__ == "__main__":
    main()
