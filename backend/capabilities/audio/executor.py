import re
import os
import subprocess
from shared.i18n import lang


def _volume_label(volume: str, response_lang: str) -> str:
    if response_lang == "de":
        return {"mute": "stumm", "unmute": "entstummt"}.get(volume, volume)
    return {"mute": "muted", "unmute": "unmuted"}.get(volume, volume)


def _playerctl_volume(player: str, app_name: str, volume: str, response_lang: str = "en") -> dict:
    """Set volume via MPRIS (playerctl) — works even when paused."""
    if volume == "mute":
        args = ["0"]
    elif volume == "unmute":
        args = ["1"]
    elif volume.startswith("+"):
        args = [f"{float(volume[1:-1]) / 100}+"]
    elif volume.startswith("-"):
        args = [f"{float(volume[1:-1]) / 100}-"]
    else:
        args = [str(float(volume.rstrip("%")) / 100)]
    subprocess.run(["playerctl", "-p", player, "volume"] + args, check=True)
    label = _volume_label(volume, response_lang)
    word = "Lautstärke" if response_lang == "de" else "volume"
    return {"success": True, "message": f"{app_name} {word}: {label}"}


def set_app_volume(app_name: str, app_cmd: str, volume: str, response_lang: str = "en") -> dict:
    # Try MPRIS first (works when paused, e.g. Spotify)
    try:
        players_out = subprocess.run(["playerctl", "-l"], capture_output=True, text=True)
        if players_out.returncode == 0:
            app_lower = app_name.lower()
            cmd_lower = os.path.basename(app_cmd).lower()
            for player in players_out.stdout.strip().splitlines():
                p = player.lower().split(".")[0]
                if p in app_lower or p in cmd_lower or app_lower in p:
                    return _playerctl_volume(player.strip(), app_name, volume, response_lang)
    except FileNotFoundError:
        pass

    # Fallback: pactl sink-inputs (only works while actively playing)
    result = subprocess.run(["pactl", "list", "sink-inputs"], capture_output=True, text=True)
    if result.returncode != 0:
        msg = "pactl nicht verfügbar." if response_lang == "de" else "pactl is not available."
        return {"success": False, "message": msg}

    search_terms = {app_name.lower(), os.path.basename(app_cmd).lower()}

    sink_ids = []
    current_id = None
    current_props = []

    for raw in result.stdout.splitlines():
        line = raw.strip()
        m = re.match(r"(?:Sink Input|Ziel-Eingabe)\s*#(\d+)", line)
        if m:
            if current_id and any(t in " ".join(current_props) for t in search_terms):
                sink_ids.append(current_id)
            current_id = m.group(1)
            current_props = []
        elif current_id and "=" in line:
            current_props.append(line.split("=", 1)[-1].strip().strip('"').lower())

    if current_id and any(t in " ".join(current_props) for t in search_terms):
        sink_ids.append(current_id)

    if not sink_ids:
        total = result.stdout.count("Ziel-Eingabe") + result.stdout.count("Sink Input")
        if response_lang == "de":
            hint = f" ({total} Streams aktiv, keiner gehört zu {app_name})" if total else " (keine aktiven Streams — läuft die App gerade?)"
            msg = f"Kein Audio-Stream für {app_name} gefunden{hint}"
        else:
            hint = f" ({total} active streams, none belong to {app_name})" if total else " (no active streams. Is the app playing audio?)"
            msg = f"No audio stream found for {app_name}{hint}"
        return {"success": False, "message": msg}

    for sid in sink_ids:
        if volume == "mute":
            subprocess.run(["pactl", "set-sink-input-mute", sid, "1"], check=True)
        elif volume == "unmute":
            subprocess.run(["pactl", "set-sink-input-mute", sid, "0"], check=True)
        else:
            subprocess.run(["pactl", "set-sink-input-volume", sid, volume], check=True)

    label = _volume_label(volume, response_lang)
    word = "Lautstärke" if response_lang == "de" else "volume"
    return {"success": True, "message": f"{app_name} {word}: {label}"}


def get_current_volume() -> str | None:
    try:
        out = subprocess.run(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            capture_output=True, text=True, timeout=2,
        )
        m = re.search(r"(\d+)%", out.stdout)
        return f"{m.group(1)}%" if m else None
    except Exception:
        return None


def execute(parsed: dict) -> dict | None:
    """Handle set_volume, media_control, set_app_volume. Returns None if action not handled."""
    action = parsed.get("action")
    target = parsed.get("target", "")
    response_lang = lang(parsed)

    if action == "set_volume":
        result = {}
        if target not in ("mute", "unmute") and not target.startswith(("+", "-")):
            prev = get_current_volume()
            if prev:
                result["prev_volume"] = prev
        if target == "mute":
            cmd = ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"]
        elif target == "unmute":
            cmd = ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"]
        else:
            cmd = ["pactl", "set-sink-volume", "@DEFAULT_SINK@", target]
        subprocess.run(cmd, check=True)
        fallback = "Lautstärke geändert." if response_lang == "de" else "Volume changed."
        return {"success": True, "message": parsed.get("app_name", fallback), **result}

    if action == "media_control":
        result = subprocess.run(["playerctl", target], capture_output=True, text=True)
        if result.returncode != 0:
            msg = "Kein Medienplayer aktiv." if response_lang == "de" else "No active media player."
            return {"success": False, "message": msg}
        fallback = "Mediensteuerung." if response_lang == "de" else "Media control."
        return {"success": True, "message": parsed.get("app_name", fallback)}

    if action == "set_app_volume":
        return set_app_volume(
            parsed.get("app_name", ""),
            parsed.get("app_cmd", ""),
            parsed.get("target", "50%"),
            response_lang,
        )

    return None
