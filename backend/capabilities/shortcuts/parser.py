import re
import json
from shared.paths import SHORTCUTS_FILE


def _load_shortcuts() -> dict:
    try:
        with open(SHORTCUTS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def parse_config_url_save(text_lower: str, text_original: str) -> dict | None:
    m = re.search(
        r"\b(?:merke\s+dir|speichere?|save|remember|store)\s+(.+?)\s+als\s+(https?://\S+|[\w][\w.-]*\.[a-z]{2,10})\s*$",
        text_original, re.IGNORECASE,
    ) or re.search(
        r"\b(?:merke\s+dir|speichere?|save|remember|store)\s+(.+?)\s+as\s+(https?://\S+|[\w][\w.-]*\.[a-z]{2,10})\s*$",
        text_original, re.IGNORECASE,
    )
    if not m:
        return None
    name = m.group(1).strip().lower()
    url_raw = m.group(2).strip()
    if not url_raw.startswith(("http://", "https://")):
        url_raw = "https://" + url_raw
    return {
        "action": "save_url",
        "target": name,
        "url": url_raw,
        "url_title": m.group(1).strip(),
        "app_name": f"URL: {m.group(1).strip()}",
        "window_title": None, "window_class": None, "flatpak_id": None,
        "layout": None, "desktop": None, "monitor": None,
    }


def parse_config_shortcut_create(text_lower: str, text_original: str) -> dict | None:
    m = (
        re.search(r"\bwenn\s+ich\s+(.+?)\s+sage[,:\s]+(.+)$", text_original, re.IGNORECASE)
        or re.search(r"\bwhen\s+I\s+say\s+(.+?)[,:\s]+(?:then\s+)?(.+)$", text_original, re.IGNORECASE)
    )
    if not m:
        return None
    name = m.group(1).strip().lower()
    action_text = m.group(2).strip()
    commands = [p.strip() for p in re.split(r"\s+(?:(?:und|and)\s+)?(?:dann|then)\s+", action_text, flags=re.IGNORECASE) if p.strip()]
    if not commands:
        return None
    return {
        "action": "save_shortcut_desc",
        "target": name,
        "shortcut_commands": commands,
        "app_name": f"Shortcut: {name}",
        "window_title": None, "window_class": None, "flatpak_id": None,
        "layout": None, "desktop": None, "monitor": None,
    }


def parse_config_shortcut_delete(text_lower: str) -> dict | None:
    m = re.search(r"\b(?:entferne?|lösche?|delete|remove)\b.{0,15}\bshortcut\b\s+(.+)$", text_lower)
    if not m:
        return None
    return {
        "action": "delete_shortcut",
        "target": m.group(1).strip(),
        "app_name": f"Shortcut: {m.group(1).strip()}",
        "window_title": None, "window_class": None, "flatpak_id": None,
        "layout": None, "desktop": None, "monitor": None,
    }


def parse_suggestion_query(text_lower: str) -> dict | None:
    if re.search(r"\b(vorschläge?|suggestions?)\b", text_lower):
        return {"action": "query_shortcut_suggestions"}
    return None


def parse_shortcut_save(text_lower: str) -> dict | None:
    m = (
        re.search(r"\bshortcut\b.{0,20}\bals\b\s+([a-zäöüß][a-zäöüß0-9\-]*)", text_lower)
        or re.search(r"\bshortcut\b.{0,20}\bas\b\s+([a-z][a-z0-9\-]*)", text_lower)
    )
    if m:
        return {"action": "save_shortcut_sequence", "name": m.group(1)}
    return None


def parse_shortcut(text_lower: str) -> dict | None:
    shortcuts = _load_shortcuts()
    for name, commands in shortcuts.items():
        if re.search(r"\b" + re.escape(name.lower()) + r"\b", text_lower):
            return {
                "action": "run_shortcut",
                "target": name,
                "app_name": name.title(),
                "shortcut_commands": commands,
                "window_title": None, "window_class": None, "flatpak_id": None,
                "layout": None, "desktop": None, "monitor": None,
            }
    return None
