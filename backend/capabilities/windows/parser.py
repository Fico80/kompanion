import re
from shared.config import _load_apps, _extract_placement
from shared.i18n import detect_language


def parse_close_app(text_lower: str) -> dict | None:
    is_de = detect_language(text_lower) == "de"
    if not re.search(r"\b(schlie[sß]e?|schlisse?|beende?|stoppe?|kill|close|quit|exit)\b|\bmach.{0,20}zu\b", text_lower):
        return None
    if re.search(r"\b(alles|alle\s+(?:fenster|apps?|programme?|anwendungen)|everything|all\s+(?:windows?|apps?|programs?))\b", text_lower):
        return {
            "action": "close_all_windows",
            "target": "all",
            "app_name": "Alle Fenster" if is_de else "All windows",
            "requires_confirmation": True,
            "confirm_prompt": "Alle Fenster schließen? Sag ja oder nein." if is_de else "Close all windows? Say yes or no.",
            "window_title": None, "window_class": None, "flatpak_id": None,
            "layout": None, "desktop": None, "monitor": None,
        }
    apps = _load_apps()
    for keyword, info in sorted(apps.items(), key=lambda x: len(x[0]), reverse=True):
        if keyword in text_lower:
            return {
                "action": "close_app",
                "target": info["class"],
                "app_name": info["name"],
                "app_cmd": info["cmd"],
                "window_class": info["class"],
                "window_title": info["title"],
                "flatpak_id": None,
                "layout": None, "desktop": None, "monitor": None,
            }
    return None


def parse_move_window(text_lower: str, text_original: str = "") -> dict | None:
    is_de = detect_language(text_original or text_lower) == "de"
    if not re.search(r"\b(verschieb[e]?|verschieben|schieb[e]?|beweg[e]?|bewegen|schick[e]?|schicken|move|send|push)\b", text_lower):
        return None

    from_match = re.search(r"\b(von|from)\s+(?:arbeitsfläche|workspace|fläche|desktop)\s*(\d+)\b", text_lower)
    from_desktop = int(from_match.group(2)) - 1 if from_match else None

    cleaned = re.sub(r"\b(von|from)\s+(?:arbeitsfläche|workspace|fläche|desktop)\s*\d+\b", "", text_lower).strip()
    layout, desktop, monitor = _extract_placement(cleaned)

    app_info = None
    app_key = None
    for key, info in _load_apps().items():
        if re.search(r'\b' + re.escape(key) + r'\b', text_lower):
            if app_info is None or len(key) > len(app_key):
                app_info = info
                app_key = key

    if not app_info:
        if re.search(r"\b(aktives?\s+fenster|aktuelles?\s+fenster|fenster|active\s+window|current\s+window|window|this\s+window)\b", text_lower):
            if layout is None and desktop is None and monitor is None:
                return {
                    "action": "needs_clarification", "clarification_type": "append",
                    "original_command": text_original or text_lower,
                    "prompt": "Wohin? Links, rechts oder Arbeitsfläche?" if is_de else "Where to? Left, right or workspace?",
                    "app_name": "Aktives Fenster" if is_de else "Active window", "window_title": None, "window_class": None,
                    "flatpak_id": None, "layout": None, "desktop": None, "monitor": None,
                }
            return {
                "action": "move_window",
                "target": "__active_window__",
                "app_name": "Aktives Fenster" if is_de else "Active window",
                "window_class": "__active_window__",
                "window_title": "",
                "flatpak_id": None,
                "layout": layout, "desktop": desktop, "monitor": monitor,
                "from_desktop": from_desktop,
                "_confident": True,
            }
        return None

    if layout is None and desktop is None and monitor is None:
        return {
            "action": "needs_clarification", "clarification_type": "append",
            "original_command": text_original or text_lower,
            "prompt": f"{app_info['name']}: Wohin? Links, rechts oder Arbeitsfläche?" if is_de else f"{app_info['name']}: Where to? Left, right or workspace?",
            "app_name": app_info["name"], "window_title": None, "window_class": None,
            "flatpak_id": None, "layout": None, "desktop": None, "monitor": None,
        }

    return {
        "action": "move_window",
        "target": app_info["cmd"],
        "app_name": app_info["name"],
        "window_class": app_info["class"],
        "window_title": "",
        "flatpak_id": app_info.get("flatpak"),
        "layout": layout, "desktop": desktop, "monitor": monitor,
        "from_desktop": from_desktop,
        "_confident": True,
    }


def parse_active_window_context_move(text_lower: str) -> dict | None:
    if not re.search(r"\b(es|das|dies(?:e|es)?|ihn|sie|fenster|app|anwendung|it|this|the\s+window|the\s+app)\b", text_lower):
        return None
    if not re.search(r"\b(mach[e]?|verschieb[e]?|schieb[e]?|beweg[e]?|bring|setz[e]?|pack|tu|move|send|put|push)\b", text_lower):
        return None

    if re.search(r"\b(zur[üu]ck|retour|wieder\s+zur[üu]ck|back)\b", text_lower):
        return {
            "action": "move_window",
            "target": "__active_window__",
            "app_name": "Aktives Fenster",
            "window_class": "__active_window__",
            "window_title": "",
            "flatpak_id": None,
            "layout": None, "desktop": None, "monitor": None,
            "from_desktop": None,
            "restore_previous": True,
            "_confident": True,
        }

    layout, desktop, monitor = _extract_placement(text_lower)
    if layout is None and desktop is None and monitor is None:
        return None

    return {
        "action": "move_window",
        "target": "__active_window__",
        "app_name": "Aktives Fenster",
        "window_class": "__active_window__",
        "window_title": "",
        "flatpak_id": None,
        "layout": layout, "desktop": desktop, "monitor": monitor,
        "from_desktop": None,
        "_confident": True,
    }
