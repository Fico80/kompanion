import subprocess
import threading
import time
from shared.i18n import lang


def set_timer(duration_seconds: int, label: str, response_lang: str = "en") -> dict:
    _id = str(time.time())

    def _fire():
        msg = label or ("Zeit abgelaufen!" if response_lang == "de" else "Time is up!")
        title = "⏰ Erinnerung" if response_lang == "de" else "⏰ Reminder"
        subprocess.run(
            ["notify-send", "-u", "normal", "-t", "10000", title, msg],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    t = threading.Timer(duration_seconds, _fire)
    t.daemon = True
    t.start()

    mins, secs = duration_seconds // 60, duration_seconds % 60
    if mins >= 60:
        h = mins // 60
        m = mins % 60
        if response_lang == "de":
            time_str = f"{h} Stunde{'n' if h != 1 else ''}" + (f" {m} min" if m else "")
        else:
            time_str = f"{h} hour{'s' if h != 1 else ''}" + (f" {m} min" if m else "")
    elif mins > 0 and secs > 0:
        time_str = f"{mins}m {secs}s"
    elif mins > 0:
        time_str = f"{mins} Minute{'n' if mins != 1 else ''}" if response_lang == "de" else f"{mins} minute{'s' if mins != 1 else ''}"
    else:
        time_str = f"{secs} Sekunde{'n' if secs != 1 else ''}" if response_lang == "de" else f"{secs} second{'s' if secs != 1 else ''}"

    suffix = f" — {label}" if label else ""
    return {"success": True, "message": f"Timer: {time_str}{suffix}"}


def execute(parsed: dict) -> dict | None:
    if parsed.get("action") == "set_timer":
        return set_timer(int(parsed.get("target", 300)), parsed.get("timer_label", ""), lang(parsed))
    return None
