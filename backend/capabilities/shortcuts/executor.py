import json
import os
import tempfile
from shared.paths import SHORTCUTS_FILE, URLS_FILE
from shared.i18n import lang


def _atomic_json_write(path: str, data) -> None:
    """Write JSON to path atomically: temp file → os.replace, so a crash never corrupts the target."""
    dir_ = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_url(parsed: dict, response_lang: str = "en") -> dict:
    with open(URLS_FILE, encoding="utf-8") as f:
        urls = json.load(f)
    name = parsed.get("target", "").strip()
    url = parsed.get("url", "")
    title = parsed.get("url_title", name.capitalize())
    existed = name in urls
    urls[name] = {"url": url, "title": title}
    _atomic_json_write(str(URLS_FILE), urls)
    verb = ("aktualisiert" if existed else "gespeichert") if response_lang == "de" else ("updated" if existed else "saved")
    return {"success": True, "message": f"URL {verb}: '{name}' → {url}"}


def delete_url(name: str, response_lang: str = "en") -> dict:
    try:
        with open(URLS_FILE, encoding="utf-8") as f:
            urls = json.load(f)
        if name not in urls:
            msg = f"URL '{name}' nicht gefunden." if response_lang == "de" else f"URL '{name}' not found."
            return {"success": False, "message": msg}
        del urls[name]
        _atomic_json_write(str(URLS_FILE), urls)
        msg = f"URL '{name}' entfernt." if response_lang == "de" else f"URL '{name}' removed."
        return {"success": True, "message": msg}
    except Exception as e:
        msg = f"Fehler: {e}" if response_lang == "de" else f"Error: {e}"
        return {"success": False, "message": msg}


def save_shortcut_desc(parsed: dict, response_lang: str = "en") -> dict:
    with open(SHORTCUTS_FILE, encoding="utf-8") as f:
        shortcuts = json.load(f)
    name = parsed.get("target", "").strip()
    commands = parsed.get("shortcut_commands", [])
    existed = name in shortcuts
    shortcuts[name] = commands
    _atomic_json_write(str(SHORTCUTS_FILE), shortcuts)
    verb = ("aktualisiert" if existed else "erstellt") if response_lang == "de" else ("updated" if existed else "created")
    return {"success": True, "message": f"Shortcut '{name}' {verb}: {' → '.join(commands)}"}


def delete_shortcut(parsed: dict, response_lang: str = "en") -> dict:
    with open(SHORTCUTS_FILE, encoding="utf-8") as f:
        shortcuts = json.load(f)
    name = parsed.get("target", "").strip()
    if name not in shortcuts:
        existing = ", ".join(shortcuts.keys()) or ("(keine)" if response_lang == "de" else "(none)")
        msg = (f"Shortcut '{name}' nicht gefunden. Vorhandene: {existing}" if response_lang == "de"
               else f"Shortcut '{name}' not found. Available: {existing}")
        return {"success": False, "message": msg}
    original_commands = shortcuts[name]
    del shortcuts[name]
    _atomic_json_write(str(SHORTCUTS_FILE), shortcuts)
    msg = (f"Shortcut '{name}' entfernt." if response_lang == "de" else f"Shortcut '{name}' removed.")
    return {"success": True, "message": msg, "original_commands": original_commands}


def query_shortcut_suggestions(response_lang: str = "en") -> dict:
    import memory as _mem
    top = _mem.get_top_sequence()
    if not top:
        msg = ("Ich habe noch keine wiederkehrenden Muster erkannt. Nutze den Assistenten noch etwas mehr."
               if response_lang == "de"
               else "No recurring patterns detected yet. Use the assistant a bit more.")
        return {"success": True, "message": msg}
    preview = " → ".join((c[:25] + "…") if len(c) > 25 else c for c in top["commands"])
    msg = (f"Vorschlag ({top['count']}×): {preview}. Sag 'Shortcut speichern als [Name]' um das als Shortcut zu speichern."
           if response_lang == "de"
           else f"Suggestion ({top['count']}×): {preview}. Say 'save shortcut as [name]' to save it.")
    return {"success": True, "message": msg}


def save_shortcut_sequence(parsed: dict, response_lang: str = "en") -> dict:
    import memory as _mem
    name = parsed.get("name", "").strip()
    if not name:
        msg = "Kein Name angegeben." if response_lang == "de" else "No name provided."
        return {"success": False, "message": msg}
    top = _mem.get_top_sequence()
    if not top:
        msg = ("Kein Muster erkannt das gespeichert werden könnte." if response_lang == "de"
               else "No pattern found that could be saved.")
        return {"success": False, "message": msg}
    with open(SHORTCUTS_FILE) as f:
        shortcuts = json.load(f)
    shortcuts[name] = top["commands"]
    _atomic_json_write(str(SHORTCUTS_FILE), shortcuts)
    steps = " → ".join(top["commands"])
    msg = (f"Shortcut '{name}' gespeichert: {steps}" if response_lang == "de"
           else f"Shortcut '{name}' saved: {steps}")
    return {"success": True, "message": msg}


def execute(parsed: dict) -> dict | None:
    action = parsed.get("action")
    response_lang = lang(parsed)
    if action == "save_url":
        return save_url(parsed, response_lang)
    if action == "delete_url":
        return delete_url(parsed.get("target") or "", response_lang)
    if action == "save_shortcut_desc":
        return save_shortcut_desc(parsed, response_lang)
    if action == "delete_shortcut":
        return delete_shortcut(parsed, response_lang)
    if action == "query_shortcut_suggestions":
        return query_shortcut_suggestions(response_lang)
    if action == "save_shortcut_sequence":
        return save_shortcut_sequence(parsed, response_lang)
    return None
