import re
import os
import json
import subprocess
import requests
from shared.config import _load_apps, _extract_placement, _load_urls
from shared.i18n import detect_language

from capabilities.audio.parser import parse_app_volume, parse_audio
from capabilities.brightness.parser import parse_brightness
from capabilities.calendar.parser import parse_create_calendar, parse_calendar_query
from capabilities.clipboard.parser import parse_clipboard
from capabilities.notes.parser import parse_note, parse_knowledge_query
from capabilities.spotify.parser import parse_spotify
from capabilities.system.parser import parse_system_query
from capabilities.tasks.parser import parse_task
from capabilities.search.parser import parse_file_search
from capabilities.shortcuts.parser import (
    parse_config_url_save, parse_config_shortcut_create, parse_config_shortcut_delete,
    parse_suggestion_query, parse_shortcut_save, parse_shortcut,
)
from capabilities.timer.parser import parse_timer
from capabilities.weather.parser import parse_weather_query
from capabilities.windows.parser import (
    parse_close_app, parse_move_window, parse_active_window_context_move,
)

# --- App / URL / Folder data ---

HOME = os.path.expanduser("~")

def _xdg(name: str) -> str:
    """Return the real XDG user directory path, falling back to English default."""
    defaults = {
        "DOWNLOAD": f"{HOME}/Downloads", "DOCUMENTS": f"{HOME}/Documents",
        "PICTURES": f"{HOME}/Pictures",  "MUSIC":     f"{HOME}/Music",
        "VIDEOS":   f"{HOME}/Videos",    "DESKTOP":   f"{HOME}/Desktop",
    }
    try:
        out = subprocess.run(["xdg-user-dir", name], capture_output=True, text=True, timeout=2)
        path = out.stdout.strip()
        if path and path != HOME:
            return path
    except Exception:
        pass
    return defaults.get(name, HOME)

STANDARD_FOLDERS = {
    "downloads":    _xdg("DOWNLOAD"),
    "dokumente":    _xdg("DOCUMENTS"),
    "documents":    _xdg("DOCUMENTS"),
    "bilder":       _xdg("PICTURES"),
    "pictures":     _xdg("PICTURES"),
    "fotos":        _xdg("PICTURES"),
    "musik":        _xdg("MUSIC"),
    "music":        _xdg("MUSIC"),
    "videos":       _xdg("VIDEOS"),
    "schreibtisch": _xdg("DESKTOP"),
    "desktop":      _xdg("DESKTOP"),
}

def _scan_home_folders(include_subdirs: bool = False) -> str:
    """Build a folder list for the LLM.
    When the LLM is local, include immediate subdirs for richer folder matching.
    When using a cloud provider, list top-level paths only to avoid leaking project names.
    """
    skip = {"snap", "venv", ".git", "__pycache__", "node_modules"}
    lines = []
    try:
        for name in sorted(os.listdir(HOME)):
            if name.startswith(".") or name in skip:
                continue
            full = os.path.join(HOME, name)
            if not os.path.isdir(full):
                continue
            if include_subdirs:
                try:
                    subdirs = sorted(
                        s for s in os.listdir(full)
                        if not s.startswith(".") and os.path.isdir(os.path.join(full, s))
                    )[:6]
                except PermissionError:
                    subdirs = []
                if subdirs:
                    lines.append(f"{full}  (subdirs: {', '.join(subdirs)})")
                    continue
            lines.append(full)
    except Exception:
        pass
    return "\n".join(lines) or "(none)"

# --- LLM config ---

_raw_url = os.environ.get("LLM_BASE_URL", "").rstrip("/")

def _is_local_llm(url: str) -> bool:
    return any(h in url for h in ("localhost", "127.0.0.1", "::1", "0.0.0.0"))

_HOME_FOLDERS = _scan_home_folders(include_subdirs=_is_local_llm(_raw_url))
_LLM_ENDPOINT = (_raw_url if _raw_url.endswith("/chat/completions") else _raw_url + "/chat/completions") if _raw_url else ""
_LLM_MODEL    = os.environ.get("LLM_MODEL", "qwen2.5:7b")
_LLM_TIMEOUT  = 10  # seconds

SYSTEM_PROMPT = f"""You are a command parser for a KDE Plasma desktop assistant on Linux.
Parse the user's command (German or English) and return ONLY a valid JSON object — no explanation, no markdown.

=== KNOWN APPS ===
firefox, browser        → target:"firefox"  app_name:"Firefox"        window_class:"firefox"        window_title:"Firefox"         flatpak_id:null
vscode, vs code, code   → target:"code"     app_name:"VS Code"        window_class:"code"           window_title:"Visual Studio Code" flatpak_id:null
konsole, terminal, console → target:"konsole"  app_name:"Konsole"        window_class:"konsole"        window_title:"Konsole"         flatpak_id:null
spotify                 → target:"spotify"  app_name:"Spotify"        window_class:"spotify"        window_title:"Spotify"         flatpak_id:"com.spotify.Client"
discord                 → target:"discord"  app_name:"Discord"        window_class:"discord"        window_title:"Discord"         flatpak_id:"com.discordapp.Discord"
zapzap, whatsapp        → target:"zapzap"   app_name:"ZapZap"         window_class:"zapzap"         window_title:"ZapZap"          flatpak_id:"com.rtosta.zapzap"
einstellungen, settings → target:"systemsettings" app_name:"System Settings" window_class:"systemsettings" window_title:"System Settings" flatpak_id:null

For unknown apps, use action "open_app" and guess the command name (lowercase).

=== KNOWN URLS ===
google     → target:"https://www.google.com"    app_name:"Google"     window_class:"firefox" window_title:"Google"
perplexity → target:"https://www.perplexity.ai" app_name:"Perplexity" window_class:"firefox" window_title:"Perplexity"
For other websites/URLs use action "open_url".

=== FOLDERS ===
Use EXACT paths from this list. Map fuzzy/informal names to the best matching path.
Examples: "Uni Sachen" → {HOME}/UNI, "Business" → {HOME}/Business, "Bilder" → {HOME}/Bilder

Standard:
  downloads  → {_xdg("DOWNLOAD")}
  dokumente  → {_xdg("DOCUMENTS")}
  bilder     → {_xdg("PICTURES")}
  musik      → {_xdg("MUSIC")}
  videos     → {_xdg("VIDEOS")}
  schreibtisch → {_xdg("DESKTOP")}

All user folders on this system:
{_HOME_FOLDERS}

For any folder: action "open_path", window_class:"dolphin", app_name:"File Manager", window_title: folder name.
For absolute paths like /home/... also use action "open_path".
IMPORTANT: Only use paths that appear in the list above — never invent paths.

=== PLACEMENT ===
layout: "left" (links/left), "right" (rechts/right), "full" (vollbild/maximiert/full), or null

IMPORTANT: "Arbeitsfläche", "Workspace", "Fläche" refer to a VIRTUAL DESKTOP NUMBER, NOT the Desktop folder.
desktop: 0-indexed integer (Arbeitsfläche 1 → 0, Arbeitsfläche 2 → 1, Arbeitsfläche 3 → 2, ...) or null

monitor: 0 (linker/left monitor/bildschirm/screen), 1 (rechter/right monitor/bildschirm/screen), or null

=== OUTPUT FORMAT ===
{{
  "action": "open_app" | "open_url" | "open_path" | "move_window" | "unknown",
  "target": "string or null",
  "app_name": "string or null",
  "window_title": "string or null",
  "window_class": "string or null",
  "flatpak_id": "string or null",
  "layout": "left" | "right" | "full" | null,
  "desktop": integer or null,
  "monitor": 0 | 1 | null,
  "from_desktop": integer or null
}}

For move_window: use verbs like verschiebe/bewege/schicke/move. "from_desktop" is the 0-indexed source desktop (e.g. "von Arbeitsfläche 2" → 1), or null to move the active window."""


# --- LLM parser ---

def _parse_with_llm(text: str) -> dict | None:
    # Always extract placement via regex — LLM is unreliable for numbers/directions
    layout, desktop, monitor = _extract_placement(text.lower())

    api_key = os.environ.get("LLM_API_KEY", "")
    if not _LLM_ENDPOINT:
        print("[LLM] Kein LLM_BASE_URL konfiguriert.")
        return None
    if not api_key and not _is_local_llm(_LLM_ENDPOINT):
        print("[LLM] Kein API-Key gesetzt (LLM_API_KEY) und kein lokaler Endpoint (LLM_BASE_URL).")
        return None

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = requests.post(
            _LLM_ENDPOINT,
            headers=headers,
            json={
                "model": _LLM_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f'Parse this command: "{text}"'},
                ],
                "temperature": 0,
                "max_tokens": 150,
                "response_format": {"type": "json_object"},
            },
            timeout=_LLM_TIMEOUT,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
        parsed = json.loads(raw)

        action = parsed.get("action", "unknown")
        target = parsed.get("target")

        if not action:
            return None
        if action in ("open_app", "open_url", "open_path") and not target:
            # Try to recover target from app_name if LLM left target null
            app_name_lower = (parsed.get("app_name") or "").lower()
            for keyword, info in sorted(_load_apps().items(), key=lambda x: len(x[0]), reverse=True):
                if app_name_lower == keyword or app_name_lower == info["name"].lower():
                    target = info["cmd"]
                    parsed.update({"app_name": info["name"], "window_title": info["title"],
                                   "window_class": info["class"], "flatpak_id": info.get("flatpak")})
                    break
            if not target:
                return None

        # Normalize target through apps table in case LLM returned an alias (e.g. "browser" → "firefox")
        if action == "open_app" and target:
            target_lower = target.lower()
            for keyword, info in sorted(_load_apps().items(), key=lambda x: len(x[0]), reverse=True):
                if target_lower == keyword:
                    target       = info["cmd"]
                    parsed["app_name"]     = info["name"]
                    parsed["window_title"] = info["title"]
                    parsed["window_class"] = info["class"]
                    parsed["flatpak_id"]   = info.get("flatpak")
                    break

        return {
            "action":       action,
            "target":       target,
            "app_name":     parsed.get("app_name"),
            "window_title": parsed.get("window_title"),
            "window_class": parsed.get("window_class"),
            "flatpak_id":   parsed.get("flatpak_id"),
            # Always use regex-extracted placement values
            "layout":       layout,
            "desktop":      desktop,
            "monitor":      monitor,
        }
    except Exception as e:
        print(f"[LLM] Unavailable, using regex fallback: {e}")
        return None


# --- Multi-open: "öffne X [placement] und Y [placement]" ---

def _parse_multi_open(text: str) -> dict | None:
    """Detect two or more simultaneous app/url opens separated by 'und' or 'and'."""
    if not re.search(r"\s+(?:und|and)\s+", text, re.IGNORECASE):
        return None
    parts = re.split(r"\s+(?:und|and)\s+", text, flags=re.IGNORECASE)
    if len(parts) < 2:
        return None
    parsed_parts = []
    for part in parts:
        r = _parse_regex(part.strip())
        if not r.get("_confident") or r.get("action") not in ("open_app", "open_url", "open_path"):
            return None
        parsed_parts.append(r)
    return {"action": "multi_open", "parts": parsed_parts}

# --- Regex fallback ---

def _parse_regex(text: str) -> dict:
    text_lower = text.lower().strip()

    monitor = None
    monitor_pattern = r"\b(linke[rnms]?|left|rechte[rnms]?|right)\s+(monitor|bildschirm|screen)\b"
    monitor_match = re.search(monitor_pattern, text_lower)
    if monitor_match:
        monitor = 0 if monitor_match.group(1).startswith("link") or monitor_match.group(1) == "left" else 1
        text_lower = re.sub(monitor_pattern, "", text_lower).strip()
    else:
        m2 = re.search(r"\b(monitor|bildschirm|screen)\s*([12])\b", text_lower)
        if m2:
            monitor = int(m2.group(2)) - 1
            text_lower = re.sub(r"\b(monitor|bildschirm|screen)\s*[12]\b", "", text_lower).strip()

    layout = None
    if re.search(r"\b(links|left)\b", text_lower):
        layout = "left"
    elif re.search(r"\b(rechts|right)\b", text_lower):
        layout = "right"
    elif re.search(r"\b(vollbild|maximiert|maximized|full)\b", text_lower):
        layout = "full"

    desktop = None
    desktop_match = re.search(r"\b(arbeitsfläche|desktop|workspace|fläche)\s*(\d+)\b", text_lower)
    if desktop_match:
        desktop = int(desktop_match.group(2)) - 1

    cleaned = text.strip()
    cleaned = re.sub(r"\b(linke[rnms]?|left|rechte[rnms]?|right)\s+(monitor|bildschirm|screen)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(monitor|bildschirm|screen)\s*[12]\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(vollbild|maximiert|maximized|full)\b", "", cleaned, flags=re.IGNORECASE)
    if layout:
        cleaned = re.sub(r"\b(links|left|rechts|right)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(arbeitsfläche|desktop|workspace|fläche)\s*\d+\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(öffne|öffnen|open|start|starte|starten|zeige?|show|mach|mache|run|execute|führe aus|navigiere|geh|gehe)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(mir|mein|meine[nm]?|meines|bitte)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(auf|on|am|an|im|den|dem|der|die|das|in|zu|zum|zur|nach|des|vom|von)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = " ".join(cleaned.split()).strip()
    cleaned_lower = cleaned.lower()

    is_explicit_folder = False
    is_explicit_file = False
    if cleaned_lower.startswith("ordner ") or cleaned_lower.startswith("folder "):
        is_explicit_folder = True
        cleaned = cleaned[7:].strip()
        cleaned_lower = cleaned_lower[7:].strip()
    elif cleaned_lower.endswith(" ordner") or cleaned_lower.endswith(" folder"):
        is_explicit_folder = True
        cleaned = cleaned[:-7].strip()
        cleaned_lower = cleaned_lower[:-7].strip()
    elif cleaned_lower.startswith("datei ") or cleaned_lower.startswith("file "):
        is_explicit_file = True
        offset = 6 if cleaned_lower.startswith("datei ") else 5
        cleaned = cleaned[offset:].strip()
        cleaned_lower = cleaned_lower[offset:].strip()

    placement = {"layout": layout, "desktop": desktop, "monitor": monitor}

    for keyword, info in _load_urls().items():
        if keyword in cleaned_lower:
            return {"action": "open_url", "target": info["url"], "app_name": info.get("title", keyword.capitalize()),
                    "window_title": info["title"], "window_class": info.get("class", "firefox"), "flatpak_id": None,
                    "_confident": True, **placement}

    for keyword, info in sorted(_load_apps().items(), key=lambda x: len(x[0]), reverse=True):
        if cleaned_lower == keyword or cleaned_lower.startswith(keyword + " "):
            return {"action": "open_app", "target": info["cmd"], "app_name": info["name"],
                    "window_title": info["title"], "window_class": info["class"],
                    "flatpak_id": info.get("flatpak"), "_confident": True, **placement}

    # Standard folder or explicit path prefix → confident match
    if cleaned_lower in STANDARD_FOLDERS or is_explicit_folder or is_explicit_file or cleaned.startswith("/"):
        raw = STANDARD_FOLDERS.get(cleaned_lower, cleaned)
        if not raw.startswith(("/", "~")):
            raw = f"~/{raw}"
        path = os.path.abspath(os.path.expanduser(raw))
        return {"action": "open_path", "target": path,
                "app_name": "File Manager" if (os.path.isdir(path) or is_explicit_folder) else "File Viewer",
                "window_title": os.path.basename(path) or "Dolphin",
                "window_class": "dolphin", "flatpak_id": None, "_confident": True, **placement}

    # Relative path that actually exists on disk → confident match
    test = os.path.expanduser(f"~/{cleaned}")
    if os.path.exists(test):
        return {"action": "open_path", "target": test,
                "app_name": "File Manager" if os.path.isdir(test) else "File Viewer",
                "window_title": cleaned, "window_class": "dolphin", "flatpak_id": None,
                "_confident": True, **placement}

    # Fuzzy home-dir match: find the longest folder name that appears as a whole word in the
    # cleaned text. Word-boundary matching prevents "pro" matching "Projects" or "fire" matching
    # "Firefox". e.g. "Uni Sachen" → ~/UNI, "mein Grom Projekt" → ~/Grom
    try:
        candidates = [
            (name, os.path.join(HOME, name))
            for name in os.listdir(HOME)
            if not name.startswith(".")
            and os.path.isdir(os.path.join(HOME, name))
            and len(name) >= 3  # ignore single-letter dirs like ~/R
            and re.search(r'(?<![a-z0-9])' + re.escape(name.lower()) + r'(?![a-z0-9])', cleaned_lower)
        ]
        if candidates:
            best_name, best_path = max(candidates, key=lambda c: len(c[0]))
            return {"action": "open_path", "target": best_path,
                    "app_name": "File Manager", "window_title": best_name,
                    "window_class": "dolphin", "flatpak_id": None,
                    "_confident": True, **placement}
    except Exception:
        pass

    # Nothing matched — not confident, let LLM try
    return {"action": "unknown", "target": None, "app_name": None,
            "window_title": None, "window_class": None, "flatpak_id": None,
            "_confident": False, **placement}


# --- Public interface ---

def parse_command(text: str) -> dict:
    text_lower = text.lower().strip()
    command_lang = detect_language(text)

    def done(result: dict, stage: str) -> dict:
        result.setdefault("lang", command_lang)
        result["_stage"] = stage
        if result.get("action") == "multi_open":
            for part in result.get("parts", []):
                part.setdefault("lang", command_lang)
        return result

    # 0. Active-window pronoun moves must beat audio ("zurück" can mean previous track).
    active_move = parse_active_window_context_move(text_lower)
    if active_move:
        return done(active_move, "move")

    # 1. Spotify commands — before audio so "Spiele den Song X" isn't eaten by play regex
    spotify = parse_spotify(text_lower, text)
    if spotify:
        return done(spotify, "spotify")

    # 2. Per-app volume — before global audio so "Spotify leiser" doesn't become global
    app_vol = parse_app_volume(text_lower)
    if app_vol:
        return done(app_vol, "app_volume")

    # 3. Audio commands — fast regex, no LLM needed
    audio = parse_audio(text_lower)
    if audio:
        return done(audio, "audio")

    # 3. Monitor brightness/contrast — ddcutil
    brightness = parse_brightness(text_lower)
    if brightness:
        return done(brightness, "brightness")

    # 4. System queries
    system = parse_system_query(text_lower)
    if system:
        return done(system, "system")

    # 5. Timer / Erinnerungen (mit Dauer — kurzfristig)
    timer = parse_timer(text_lower, text)
    if timer:
        return done(timer, "timer")

    # 5b. Aufgaben / Todos (datumsbasiert oder ohne Frist — vor Kalender)
    task = parse_task(text_lower, text)
    if task:
        return done(task, "task")

    # 6. Config: URL speichern / Shortcut anlegen oder löschen
    config_url = parse_config_url_save(text_lower, text)
    if config_url:
        return done(config_url, "config_url")

    config_sc_create = parse_config_shortcut_create(text_lower, text)
    if config_sc_create:
        return done(config_sc_create, "config_shortcut_create")

    config_sc_del = parse_config_shortcut_delete(text_lower)
    if config_sc_del:
        return done(config_sc_del, "config_shortcut_delete")

    # 7. Voice notes — "Notiz: ..." / "Merke ..." / "Notiere ..."
    note = parse_note(text)
    if note:
        return done(note, "notiz")

    # 7b. Wissenssuche über gespeicherte Notizen (vor Clipboard & Dateisuche)
    knowledge = parse_knowledge_query(text_lower, text)
    if knowledge:
        return done(knowledge, "wissen")

    # 7. Clipboard tasks — "Übersetze das", "Fasse zusammen", "Erkläre das", "Verbessere das"
    clipboard = parse_clipboard(text)
    if clipboard:
        return done(clipboard, "clipboard")

    # 8. Calendar event creation — before query so "erstelle Termin" isn't misrouted
    cal_create = parse_create_calendar(text_lower, text)
    if cal_create:
        return done(cal_create, "kalender_neu")

    # 9. Calendar queries
    calendar = parse_calendar_query(text_lower)
    if calendar:
        return done(calendar, "kalender")

    # 10. Weather queries
    weather = parse_weather_query(text_lower, text)
    if weather:
        return done(weather, "wetter")

    # 11. File search
    file_search = parse_file_search(text)
    if file_search:
        return done(file_search, "suche")

    # 13. Move existing window
    move = parse_move_window(text_lower, text)
    if move:
        return done(move, "move")

    # 14. Close app — "schließe Firefox", "beende VS Code"
    close = parse_close_app(text_lower)
    if close:
        return done(close, "close")

    # 15. Shortcuts (shortcuts.json — user-editable)
    shortcut = parse_shortcut(text_lower)
    if shortcut:
        return done(shortcut, "shortcut")

    # 14. Sequence suggestions & shortcut save
    save = parse_shortcut_save(text_lower)
    if save:
        return done(save, "shortcut_save")
    suggestion = parse_suggestion_query(text_lower)
    if suggestion:
        return done(suggestion, "suggestion")

    # 15. Multi-open: "öffne X [placement] und Y [placement]"
    multi = _parse_multi_open(text)
    if multi:
        return done(multi, "multi")

    # 16. Regex — known apps/urls/folders
    result = _parse_regex(text)
    if result.get("_confident"):
        return done(result, "regex")

    # 17. LLM — fallback for unrecognized commands
    llm_result = _parse_with_llm(text)
    if llm_result:
        return done(llm_result, "llm")

    return done(result, "fallback")
