import os
import re
import shutil
import subprocess
from shared.i18n import lang


def _ddc_display_args(monitor: int | None) -> list[str]:
    if monitor is None:
        return []

    env_key = "DDCUTIL_LEFT_DISPLAY" if monitor == 0 else "DDCUTIL_RIGHT_DISPLAY"
    display = os.environ.get(env_key, str(monitor + 1))
    return ["--display", display]


def _ddc_all_display_args() -> list[list[str]]:
    try:
        detected = subprocess.run(
            ["ddcutil", "detect"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        displays = re.findall(r"^Display\s+(\d+)", detected.stdout, flags=re.MULTILINE)
        if displays:
            return [["--display", d] for d in displays]
    except Exception:
        pass
    # Fallback: use configured display indices from env
    left  = os.environ.get("DDCUTIL_LEFT_DISPLAY",  "1")
    right = os.environ.get("DDCUTIL_RIGHT_DISPLAY", "2")
    return [["--display", left], ["--display", right]]


def _parse_ddc_brightness(output: str) -> int | None:
    match = re.search(r"current value\s*=\s*(\d+)", output)
    if match:
        return int(match.group(1))
    return None


def set_brightness(target: str, monitor: int | None, response_lang: str = "en") -> dict:
    if not shutil.which("ddcutil"):
        msg = "ddcutil ist nicht installiert." if response_lang == "de" else "ddcutil is not installed."
        return {"success": False, "message": msg}

    display_arg_sets = [_ddc_display_args(monitor)] if monitor is not None else _ddc_all_display_args()
    if response_lang == "de":
        label = "alle Monitore" if monitor is None else ("linker Monitor" if monitor == 0 else "rechter Monitor")
    else:
        label = "all monitors" if monitor is None else ("left monitor" if monitor == 0 else "right monitor")

    try:
        values = []
        for display_args in display_arg_sets:
            if target.startswith(("+", "-")):
                current = subprocess.run(
                    ["ddcutil", *display_args, "getvcp", "10"],
                    capture_output=True,
                    text=True,
                    timeout=4,
                )
                if current.returncode != 0:
                    return {
                        "success": False,
                        "message": (
                            f"Helligkeit konnte nicht gelesen werden: {current.stderr.strip() or current.stdout.strip()}"
                            if response_lang == "de"
                            else f"Brightness could not be read: {current.stderr.strip() or current.stdout.strip()}"
                        ),
                    }

                current_value = _parse_ddc_brightness(current.stdout)
                if current_value is None:
                    msg = "ddcutil hat keinen Helligkeitswert geliefert." if response_lang == "de" else "ddcutil did not return a brightness value."
                    return {"success": False, "message": msg}

                delta = int(target.rstrip("%"))
                value = max(0, min(current_value + delta, 100))
            else:
                value = max(0, min(int(target.rstrip("%")), 100))

            result = subprocess.run(
                ["ddcutil", *display_args, "setvcp", "10", str(value)],
                capture_output=True,
                text=True,
                timeout=6,
            )
            if result.returncode != 0:
                return {
                    "success": False,
                    "message": (
                        f"Helligkeit konnte nicht gesetzt werden: {result.stderr.strip() or result.stdout.strip()}"
                        if response_lang == "de"
                        else f"Brightness could not be set: {result.stderr.strip() or result.stdout.strip()}"
                    ),
                }
            values.append(value)

        value_text = f"{values[0]}%" if len(set(values)) == 1 else ", ".join(f"{v}%" for v in values)
        word = "Helligkeit" if response_lang == "de" else "Brightness"
        return {"success": True, "message": f"{word} {label}: {value_text}."}

    except ValueError:
        msg = f"Ungültiger Helligkeitswert: {target}" if response_lang == "de" else f"Invalid brightness value: {target}"
        return {"success": False, "message": msg}
    except subprocess.TimeoutExpired:
        msg = "ddcutil antwortet nicht. Ist DDC/CI am Monitor aktiviert?" if response_lang == "de" else "ddcutil is not responding. Is DDC/CI enabled on the monitor?"
        return {"success": False, "message": msg}


def execute(parsed: dict) -> dict | None:
    if parsed.get("action") == "set_brightness":
        return set_brightness(parsed.get("target", ""), parsed.get("monitor"), lang(parsed))
    return None
