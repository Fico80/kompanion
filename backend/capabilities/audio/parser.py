import re
from shared.config import _load_apps
from shared.i18n import detect_language

def _audio_result(action: str, target: str, label: str) -> dict:
    return {
        "action": action, "target": target, "app_name": label,
        "window_title": None, "window_class": None, "flatpak_id": None,
        "layout": None, "desktop": None, "monitor": None,
    }

def parse_app_volume(text_lower: str) -> dict | None:
    """Per-app volume: 'Spotify leiser', 'Firefox auf 40%', 'Discord stumm'."""
    vol_keyword = re.search(
        r"\b(\d+)\s*%"
        r"|\b(lautstärke|volume)\s+(?:auf\s+|to\s+)?(\d+)\b"
        r"|\b(leiser|lauter|quieter|louder|lower|raise|stumm(?:e|en|t)?|stoom[e]?|stume[n]?|mute[d]?|stummschalten|entstummen?|unmute|ton\s*an|ton\s*aus)\b",
        text_lower,
    )
    if not vol_keyword:
        return None
    apps = _load_apps()
    for keyword, info in sorted(apps.items(), key=lambda x: len(x[0]), reverse=True):
        if keyword not in text_lower:
            continue
        m_pct = re.search(r"\b(\d+)\s*%|\b(?:lautstärke|volume)\s+(?:auf\s+|to\s+)?(\d+)\b", text_lower)
        if m_pct:
            val = m_pct.group(1) or m_pct.group(2)
            volume = f"{val}%"
        elif re.search(r"\b(entstummen?|unmute|laut\s*machen|ton\s*an|turn\s+on|sound\s+on)\b", text_lower):
            volume = "unmute"
        elif re.search(r"\b(stumm(?:e|en|t)?|stoom[e]?|stume[n]?|stimme[n]?|mute[d]?|stummschalten|ton\s*aus|sound\s+off|turn\s+off)\b", text_lower):
            volume = "mute"
        elif re.search(r"\b(leiser|quieter|lower|volume\s+down|turn\s+down)\b", text_lower):
            volume = "-10%"
        elif re.search(r"\b(lauter|louder|raise|volume\s+up|turn\s+up)\b", text_lower):
            volume = "+10%"
        else:
            continue
        return {
            "action": "set_app_volume",
            "target": volume,
            "app_name": info["name"],
            "app_cmd": info["cmd"],
            "window_class": info["class"],
            "window_title": info["title"],
            "flatpak_id": None,
            "layout": None, "desktop": None, "monitor": None,
        }
    return None

def parse_audio(text_lower: str) -> dict | None:
    is_de = detect_language(text_lower) == "de"
    if re.search(r"\bton an\b|\b(unmute|entstummen?en|laut\s+machen|laut\s+stellen|sound\s+on|turn\s+on\s+sound|enable\s+sound)\b", text_lower):
        return _audio_result("set_volume", "unmute", "Ton an" if is_de else "Sound on")

    if re.search(r"\bton aus\b|\b(stumm|mute|lautlos|stummschalten|stummstellen|sound\s+off|turn\s+off\s+sound|disable\s+sound|silence)\b", text_lower):
        return _audio_result("set_volume", "mute", "Ton aus" if is_de else "Sound off")

    m = re.search(r"\b(lautstärke|volume|lautheit)\s+(?:auf\s+|to\s+|set\s+to\s+)?(\d+)\s*(?:prozent|%)?\b", text_lower)
    if m:
        val = min(int(m.group(2)), 150)
        return _audio_result("set_volume", f"{val}%", f"Lautstärke {val}%" if is_de else f"Volume {val}%")

    if re.search(r"\b(lauter|louder|volume up|hochdrehen|lauter\s+stellen|turn\s+up|raise\s+volume|increase\s+volume)\b", text_lower):
        step = re.search(r"(\d+)\s*(?:prozent|%)", text_lower)
        n = step.group(1) if step else "10"
        return _audio_result("set_volume", f"+{n}%", f"Lauter +{n}%" if is_de else f"Louder +{n}%")

    if re.search(r"\b(leiser|quieter|volume down|runterdrehen|leiser\s+stellen|turn\s+down|lower\s+volume|decrease\s+volume)\b", text_lower):
        step = re.search(r"(\d+)\s*(?:prozent|%)", text_lower)
        n = step.group(1) if step else "10"
        return _audio_result("set_volume", f"-{n}%", f"Leiser -{n}%" if is_de else f"Quieter -{n}%")

    if re.search(r"\b(nächste[rns]?|next|skip|überspringen|weiter)\b", text_lower) and \
       not re.search(r"\b(termin[e]?|kalender|woche|calendar)\b", text_lower) and \
       (re.search(r"\b(song|lied|track|musik|titel|music)\b", text_lower) or
        re.search(r"\b(skip|next|überspringen)\b", text_lower)):
        return _audio_result("media_control", "next", "Nächster Track" if is_de else "Next track")

    if re.search(r"\b(vorherige[rns]?|previous|zurück|letzte[rns]?\s+(song|lied|track)|go\s+back)\b", text_lower):
        return _audio_result("media_control", "previous", "Vorheriger Track" if is_de else "Previous track")

    if re.search(r"\b(stop|stopp|stoppen|anhalten|aufhören|halt)\b|\bmusik\s+(aus|beenden|stopp|stoppen)\b|\bhalte?\b.{0,25}\ban\b|\bstop\s+(music|playback|playing)\b", text_lower):
        return _audio_result("media_control", "stop", "Stoppen" if is_de else "Stop")
    if re.search(r"\bstoppe\b", text_lower) and re.search(r"\b(musik|lied|song|track|abspielen|wiedergabe|music)\b", text_lower):
        return _audio_result("media_control", "stop", "Stoppen" if is_de else "Stop")

    if re.search(r"\b(pause|pausier[et]?|pausieren|pauzier[et]?|pauzieren|unterbrechen)\b|\bmusik\s+(pause|pausieren|pausiert)\b", text_lower):
        return _audio_result("media_control", "play-pause", "Pause")

    if re.search(r"\b(play|weiterspielen|fortsetzen|abspielen|spielen|resume|continue\s+playing)\b|\bspiele?\b.{0,25}\b(ab|musik|lied|song|track)\b|\bmusik\s+(an|start|abspielen|spielen|ab)\b|\bstarte\s+(musik|lied|song|track)\b|\bmach\s+(die\s+)?musik\s+an\b", text_lower):
        return _audio_result("media_control", "play", "Abspielen" if is_de else "Play")

    return None
