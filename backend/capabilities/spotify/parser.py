import re


def parse_spotify(text_lower: str, text_original: str) -> dict | None:
    def _result(action, target, query=None, label="Spotify"):
        return {
            "action": action,
            "target": target,
            "query": query,
            "app_name": label,
            "window_title": None,
            "window_class": None,
            "flatpak_id": None,
            "layout": None,
            "desktop": None,
            "monitor": None,
        }

    # "Was läuft gerade", "Was spielt gerade", "What's playing"
    if re.search(r"\b(was\s+(läuft|spielt|läuft\s+gerade|spielt\s+gerade)|welche[rns]?\s+song|aktuell(er)?\s+(song|track|lied)|was\s+höre\s+ich"
                 r"|what'?s\s+playing|what\s+song\s+is\s+this|current\s+song|now\s+playing)\b", text_lower):
        return _result("query_spotify", "current", label="Aktueller Song")

    # "Spiele Playlist Chill" / "Play playlist Deep Focus"
    m = re.search(r"\b(spiele?|öffne?|starte?|play|open|start)\s+playlist\s+(.+)", text_lower)
    if m:
        query = re.sub(r"\b(spiele?|öffne?|starte?|play|open|start)\s+playlist\s+", "", text_original, flags=re.IGNORECASE).strip()
        return _result("control_spotify", "search_playlist", query, "Playlist")

    # "Spiele Songs von [Artist]" / "Play music by [Artist]"
    m = re.search(r"\b(spiele?\s+(?:songs?\s+von|musik\s+von|etwas\s+von)|play\s+(?:songs?\s+by|music\s+by|something\s+by|anything\s+by))\s+(.+)", text_lower)
    if m:
        query = m.group(2).strip()
        return _result("control_spotify", "search_artist", query, f"Artist: {query}")

    # "Spiele von [Artist] [Song]" / "Play by [Artist] [Song]" — reversed word order
    m = re.search(r"\b(spiele?\s+von|play\s+by)\s+(\w+(?:\s+\w+)?)\s+(.+)", text_lower)
    if m:
        artist = m.group(2).strip()
        song = m.group(3).strip()
        query = f"track:{song} artist:{artist}"
        return _result("control_spotify", "search_track", query, f"♪ {song} — {artist}")

    # "Spiele [Song] von [Artist]" / "Play [Song] by [Artist]" — most precise
    m = re.search(r"\b(spiele?|play)\s+(?:(?:den|das|die|the)\s+)?(?:song|lied|track\s+)?(.+?)\s+(von|by)\s+(.+)", text_lower)
    if m:
        song = m.group(2).strip()
        artist = m.group(4).strip()
        query = f"track:{song} artist:{artist}"
        return _result("control_spotify", "search_track", query, f"♪ {song} — {artist}")

    # "Spiele den Song [name]" / "Play the song [name]"
    m = re.search(r"\b(spiele?|play)\s+(?:(?:den|das|die|the)\s+)?(?:song|lied|track)\s+(.+)", text_lower)
    if m:
        query = m.group(2).strip()
        return _result("control_spotify", "search_track", query, f"Song: {query}")

    # "Spiele [Songname]" / "Play [Songname]" — catch-all
    m = re.search(r"\b(spiele?|play)\s+(.+)", text_lower)
    if m:
        query = m.group(2).strip()
        return _result("control_spotify", "search_track", query, f"Song: {query}")

    return None
