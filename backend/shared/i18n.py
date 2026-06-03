import re


EN_WORDS = {
    "open", "start", "show", "move", "send", "close", "quit", "window", "workspace",
    "left", "right", "monitor", "screen", "volume", "mute", "unmute", "play", "pause",
    "next", "stop", "music", "weather", "calendar", "event", "appointment", "task",
    "todo", "remind", "today", "tomorrow", "week", "file", "folder", "search", "find",
    "note", "notes", "translate", "summarize", "explain", "improve", "brightness",
}

DE_WORDS = {
    "öffne", "oeffne", "starte", "zeige", "verschiebe", "schiebe", "schließe",
    "schliesse", "beende", "fenster", "arbeitsfläche", "arbeitsflaeche", "links",
    "rechts", "monitor", "bildschirm", "lautstärke", "lautstaerke", "leiser",
    "lauter", "stumm", "musik", "wetter", "kalender", "termin", "aufgabe",
    "erinnere", "heute", "morgen", "woche", "datei", "ordner", "suche", "finde",
    "notiz", "notizen", "übersetze", "uebersetze", "erkläre", "erklaere",
    "verbessere", "helligkeit", "wie", "viel", "nutze", "benutze", "habe", "steht",
    "was", "welche", "zeig", "mach", "zurück", "zurueck", "ja", "nein",
}


def detect_language(text: str | None) -> str:
    """Best-effort command language detection. Defaults to English for public use."""
    if not text:
        return "en"
    text_l = text.lower()
    tokens = set(re.findall(r"[a-zäöüß]+", text_l))
    de_score = len(tokens & DE_WORDS)
    en_score = len(tokens & EN_WORDS)
    if re.search(r"[äöüß]", text_l):
        de_score += 2
    return "de" if de_score > en_score else "en"


def lang(parsed: dict | None) -> str:
    return (parsed or {}).get("lang") or "en"


def choose(parsed: dict | None, de: str, en: str) -> str:
    return de if lang(parsed) == "de" else en
