import subprocess
import shutil
import os
import time
import kwin_client
from capabilities.audio import executor as _audio_exec
from capabilities.brightness import executor as _brightness_exec
from capabilities.calendar import executor as _calendar_exec
from capabilities.clipboard import executor as _clipboard_exec
from capabilities.notes import executor as _notes_exec
from capabilities.search import executor as _search_exec
from capabilities.shortcuts import executor as _shortcuts_exec
from capabilities.spotify import executor as _spotify_exec
from capabilities.system import executor as _system_exec
from capabilities.tasks import executor as _tasks_exec
from capabilities.timer import executor as _timer_exec
from capabilities.weather import executor as _weather_exec
from capabilities.windows import executor as _windows_exec
from shared.i18n import lang




def _run_shortcut(name: str, commands: list, response_lang: str = "en") -> dict:
    import parser as _parser
    for cmd in commands:
        parsed = _parser.parse_command(cmd)
        result = execute_parsed_intent(parsed)
        if not result.get("success"):
            msg = (f"Fehler bei '{cmd}': {result.get('message')}" if response_lang == "de"
                   else f"Error at '{cmd}': {result.get('message')}")
            return {"success": False, "message": msg}
        time.sleep(0.4)
    msg = (f"Shortcut '{name}': {len(commands)} Befehle ausgeführt." if response_lang == "de"
           else f"Shortcut '{name}': {len(commands)} commands executed.")
    return {"success": True, "message": msg}


def execute_parsed_intent(parsed: dict) -> dict:
    """
    Launches the target action and schedules window formatting via KWin.
    
    Returns a status dictionary with:
    - success: bool
    - message: str (user-friendly description)
    - details: dict of parsed info
    """
    action = parsed.get("action", "unknown")
    response_lang = lang(parsed)
    target = parsed.get("target")
    layout = parsed.get("layout")
    desktop = parsed.get("desktop")
    monitor = parsed.get("monitor")
    window_class = parsed.get("window_class", "")
    window_title = parsed.get("window_title", "")
    
    if action == "clipboard_task":
        return _clipboard_exec.execute(parsed)

    if action in ("save_note", "query_notes", "append_note"):
        return _notes_exec.execute(parsed)

    if action in ("search_files", "delete_file"):
        return _search_exec.execute(parsed)

    if action in ("save_url", "delete_url", "save_shortcut_desc", "delete_shortcut",
                  "query_shortcut_suggestions", "save_shortcut_sequence"):
        return _shortcuts_exec.execute(parsed)

    # Delegate window management actions
    if action in ("move_window", "close_app", "close_all_windows"):
        return _windows_exec.execute(parsed)

    if action == "set_brightness":
        return _brightness_exec.execute(parsed)

    target_optional = action in ("query_weather", "query_system", "query_spotify", "query_calendar",
                                 "set_timer", "create_calendar_event", "run_shortcut", "multi_open")
    if action == "unknown" or (not target and not target_optional):
        msg = (
            "Befehl nicht verstanden. Bitte versuche z.B. 'Öffne Firefox' oder 'Öffne Google rechts'."
            if response_lang == "de"
            else "Command not understood. Try something like 'open Firefox' or 'open Google on the right'."
        )
        return {
            "success": False,
            "message": msg
        }

    try:
        # Delegate Spotify actions to the Spotify capability
        if action in ("query_spotify", "control_spotify"):
            return _spotify_exec.execute(parsed)

        # Delegate system information queries to the system capability
        if action == "query_system":
            return _system_exec.execute(parsed)

        # Delegate weather queries to the weather capability
        if action == "query_weather":
            return _weather_exec.execute(parsed)

        # Delegate audio actions to the audio capability
        if action in ("set_volume", "media_control", "set_app_volume"):
            return _audio_exec.execute(parsed)

        # Delegate task actions to the tasks capability
        if action in ("add_task", "query_tasks", "complete_task", "reopen_task", "delete_task"):
            return _tasks_exec.execute(parsed)

        # Delegate timer actions to the timer capability
        if action == "set_timer":
            return _timer_exec.execute(parsed)

        # Delegate calendar actions to the calendar capability
        if action in ("create_calendar_event", "query_calendar"):
            return _calendar_exec.execute(parsed)

        extras = {}  # extra fields forwarded to the result (e.g. prev_volume for undo)
        # 1. Execute the system call based on the action
        if action == "open_app":
            flatpak_id = parsed.get("flatpak_id")
            if not shutil.which(target) and flatpak_id and shutil.which("flatpak"):
                cmd = ["flatpak", "run", flatpak_id]
            else:
                cmd = [target]
                
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            message = f"Starte Anwendung '{parsed['app_name']}'." if response_lang == "de" else f"Starting app '{parsed['app_name']}'."
            
        elif action == "open_url":
            # If layout/desktop/monitor properties are requested, force a new window
            # so that KWin can detect the newly added window and position it correctly.
            if layout is not None or desktop is not None or monitor is not None:
                cmd = ["firefox", "--new-window", target]
            else:
                cmd = ["xdg-open", target]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            message = f"Öffne URL '{target}' im Standardbrowser." if response_lang == "de" else f"Opening URL '{target}' in the default browser."
            
        elif action == "open_path":
            if not os.path.exists(target):
                msg = f"Pfad '{target}' existiert nicht auf diesem Rechner." if response_lang == "de" else f"Path '{target}' does not exist on this computer."
                return {
                    "success": False,
                    "message": msg
                }
            # If it's a directory and we need window control, force Dolphin to open in a new window.
            if os.path.isdir(target) and (layout is not None or desktop is not None or monitor is not None):
                cmd = ["dolphin", "--new-window", target]
            else:
                cmd = ["xdg-open", target]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            message = f"Öffne Pfad '{target}'." if response_lang == "de" else f"Opening path '{target}'."
            
        elif action == "multi_open":
            parts = parsed.get("parts", [])
            for p in parts:
                r = execute_parsed_intent(p)
                if not r.get("success"):
                    msg = f"Fehler bei '{p.get('app_name', '?')}': {r.get('message')}" if response_lang == "de" else f"Error with '{p.get('app_name', '?')}': {r.get('message')}"
                    return {"success": False, "message": msg}
                time.sleep(0.5)
            names = ", ".join(p.get("app_name", "?") for p in parts)
            msg = f"{len(parts)} Apps geöffnet: {names}" if response_lang == "de" else f"{len(parts)} apps opened: {names}"
            return {"success": True, "message": msg}

        elif action == "run_shortcut":
            return _run_shortcut(parsed.get("target", ""), parsed.get("shortcut_commands", []), response_lang)

        else:
            msg = f"Aktion '{action}' wird nicht unterstützt." if response_lang == "de" else f"Action '{action}' is not supported."
            return {"success": False, "message": msg}
            
        # 2. Position the window if any layout, desktop or monitor parameters are specified
        rules_applied = False
        if layout is not None or desktop is not None or monitor is not None:
            # Apply KWin window placement rules
            rules_applied = kwin_client.apply_window_rules(
                window_class=window_class,
                window_title=window_title,
                layout=layout,
                desktop=desktop,
                monitor=monitor
            )
            if not rules_applied:
                return {
                    "success": False,
                    "message": (
                        f"{message} Fensterregel konnte nicht angewendet werden. Ist KWin/qdbus-qt6 verfügbar?"
                        if response_lang == "de"
                        else f"{message} Window rule could not be applied. Is KWin/qdbus-qt6 available?"
                    ),
                    "details": {
                        "action": action,
                        "target": target,
                        "layout": layout,
                        "desktop": desktop,
                        "monitor": monitor,
                        "rules_applied": False
                    }
                }
            
        return {
            "success": True,
            "message": message,
            **extras,
            "details": {
                "action": action,
                "target": target,
                "layout": layout,
                "desktop": desktop,
                "monitor": monitor,
                "rules_applied": rules_applied
            }
        }
        
    except Exception as e:
        print(f"Execution Error: {e}")
        msg = f"Ausführungsfehler: {str(e)}" if response_lang == "de" else f"Execution error: {str(e)}"
        return {"success": False, "message": msg}
