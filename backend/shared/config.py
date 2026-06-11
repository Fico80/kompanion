import re
import os
import json
from pathlib import Path
from shared.paths import APPS_FILE, URLS_FILE
from shared.numbers import NUMBER_PATTERN, parse_number

_apps_cache: dict | None = None
_apps_mtime: float = 0.0
_urls_cache: dict | None = None
_urls_mtime: float = 0.0


def _alias_map(data: dict) -> dict:
    return {
        str(k).strip().lower(): v
        for k, v in data.items()
        if not str(k).startswith("_") and str(k).strip()
    }


def _load_urls() -> dict:
    global _urls_cache, _urls_mtime
    try:
        mtime = os.path.getmtime(URLS_FILE)
        if _urls_cache is not None and mtime == _urls_mtime:
            return _urls_cache
        with open(URLS_FILE) as f:
            data = json.load(f)
        _urls_cache = _alias_map(data)
        _urls_mtime = mtime
        return _urls_cache
    except Exception:
        return _urls_cache if _urls_cache is not None else {}


def _load_apps() -> dict:
    global _apps_cache, _apps_mtime
    try:
        local_file = Path(APPS_FILE).with_name("apps.local.json")
        app_files = [Path(APPS_FILE)]
        if local_file.exists():
            app_files.append(local_file)
        mtime = tuple(os.path.getmtime(path) for path in app_files)
        if _apps_cache is not None and mtime == _apps_mtime:
            return _apps_cache
        data = {}
        for path in app_files:
            with open(str(path)) as f:
                loaded = json.load(f)
            data.update(_alias_map(loaded))
        _apps_cache = _alias_map(data)
        _apps_mtime = mtime
        return _apps_cache
    except Exception:
        return _apps_cache if _apps_cache is not None else {}


def _extract_placement(text_lower: str) -> tuple:
    monitor = None
    monitor_pattern = (
        r"\b(?:auf|an|zum|zu|in|auf\s+den|auf\s+dem)?\s*(?:den|dem|der)?\s*"
        r"(linke[nm]?|linker|linkem|linken|left|rechte[nm]?|rechter|rechtem|rechten|right)"
        r"\s+(monitor|bildschirm|screen)\b"
    )
    m = re.search(monitor_pattern, text_lower)
    if m:
        monitor = 0 if m.group(1).startswith("link") or m.group(1) == "left" else 1
    else:
        m2 = re.search(r"\b(monitor|bildschirm|screen)\s*([12])\b", text_lower)
        if m2:
            monitor = int(m2.group(2)) - 1

    layout = None
    stripped = re.sub(monitor_pattern, "", text_lower)
    stripped = re.sub(r"\b(monitor|bildschirm|screen)\s*[12]\b", "", stripped)
    if re.search(r"\b(links|left)\b", stripped):
        layout = "left"
    elif re.search(r"\b(rechts|right)\b", stripped):
        layout = "right"
    elif re.search(r"\b(vollbild|maximiert|maximized|full)\b", text_lower):
        layout = "full"

    desktop = None
    dm = re.search(
        rf"\b(?:auf|an|zu|zur|in)?\s*(?:die|der)?\s*(arbeitsfläche|desktop|workspace|fläche)\s*({NUMBER_PATTERN})\b",
        text_lower,
    )
    if dm:
        desktop = parse_number(dm.group(2)) - 1

    return layout, desktop, monitor
