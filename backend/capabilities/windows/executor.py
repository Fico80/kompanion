import time
import kwin_client
from shared.i18n import lang


def close_all_windows(response_lang: str = "en") -> dict:
    js = """
var clients = workspace.windowList();
var count = 0;
for (var i = 0; i < clients.length; i++) {
    var c = clients[i];
    if (c.normalWindow && c.closeable && !c.skipTaskbar) {
        c.closeWindow();
        count++;
    }
}
"""
    ok = kwin_client.load_and_run_kwin_script(js, f"kompanion_close_all_{kwin_client.generate_random_id()}")
    if not ok:
        msg = "Fenster konnten nicht geschlossen werden. Ist KWin/qdbus-qt6 verfügbar?" if response_lang == "de" else "Windows could not be closed. Is KWin/qdbus-qt6 available?"
        return {"success": False, "message": msg}
    msg = "Alle Fenster geschlossen." if response_lang == "de" else "All windows closed."
    return {"success": True, "message": msg}


def close_app(window_class: str, app_name: str, response_lang: str = "en") -> dict:
    safe_class = kwin_client._js_escape(window_class.lower())
    js = f"""
var clients = workspace.windowList();
for (var i = 0; i < clients.length; i++) {{
    if (clients[i].resourceClass.toLowerCase().indexOf("{safe_class}") !== -1) {{
        clients[i].closeWindow();
    }}
}}
    """
    kwin_client.load_and_run_kwin_script(js, f"kompanion_close_{kwin_client.generate_random_id()}")
    msg = f"{app_name} geschlossen." if response_lang == "de" else f"{app_name} closed."
    return {"success": True, "message": msg}


def move_window(parsed: dict) -> dict:
    response_lang = lang(parsed)
    if parsed.get("restore_previous"):
        if kwin_client.restore_last_window_state():
            time.sleep(0.25)
            msg = "Fenster zurück verschoben." if response_lang == "de" else "Window moved back."
            return {"success": True, "message": msg}
        msg = "Ich habe keine vorherige Fensterposition gespeichert." if response_lang == "de" else "I do not have a previous window position saved."
        return {"success": False, "message": msg}

    layout     = parsed.get("layout")
    desktop    = parsed.get("desktop")
    monitor    = parsed.get("monitor")
    from_desktop = parsed.get("from_desktop")
    window_class = parsed.get("window_class", "")
    window_title = parsed.get("window_title", "")

    if layout is None and desktop is None and monitor is None:
        msg = "Wohin soll das Fenster? Bitte Ziel angeben (z.B. 'auf Arbeitsfläche 2' oder 'links')." if response_lang == "de" else "Where should the window go? Please specify a target, for example 'workspace 2' or 'left'."
        return {"success": False, "message": msg}

    print(
        f"[MOVE] target={parsed.get('target')!r} class={window_class!r} title={window_title!r} "
        f"layout={layout!r} desktop={desktop!r} monitor={monitor!r}"
    )
    try:
        rules_applied = kwin_client.apply_window_rules(
            window_class=window_class,
            window_title=window_title,
            layout=layout,
            desktop=desktop,
            monitor=monitor,
            new_window=False,
            from_desktop=from_desktop,
        )
    except Exception as e:
        msg = f"KWin-Fehler: {e}" if response_lang == "de" else f"KWin error: {e}"
        return {"success": False, "message": msg}

    if not rules_applied:
        msg = "Fensterregel konnte nicht angewendet werden. Ist KWin/qdbus-qt6 verfügbar?" if response_lang == "de" else "Window rule could not be applied. Is KWin/qdbus-qt6 available?"
        return {"success": False, "message": msg}

    time.sleep(0.25)
    app_name = parsed.get("app_name", "Fenster")
    dest = []
    if desktop is not None:
        dest.append(f"Arbeitsfläche {desktop + 1}" if response_lang == "de" else f"workspace {desktop + 1}")
    if layout:
        dest.append(layout)
    if monitor is not None:
        dest.append(f"Monitor {monitor}" if response_lang == "de" else f"monitor {monitor}")
    return {"success": True, "message": f"{app_name} → {', '.join(dest)}."}


def execute(parsed: dict) -> dict | None:
    """Handle move_window, close_app, close_all_windows. Returns None if action not handled."""
    action = parsed.get("action")
    response_lang = lang(parsed)

    if action == "move_window":
        return move_window(parsed)

    if action == "close_app":
        return close_app(parsed.get("window_class", ""), parsed.get("app_name", "App"), response_lang)

    if action == "close_all_windows":
        return close_all_windows(response_lang)

    return None
