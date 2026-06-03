from shared.i18n import lang


def _spotify_check(response_lang: str = "en") -> str | None:
    import auth.spotify as sa
    if not sa.is_authenticated():
        return "Spotify nicht verbunden. Öffne http://127.0.0.1:8000/spotify/auth im Browser." if response_lang == "de" else "Spotify is not connected. Open http://127.0.0.1:8000/spotify/auth in your browser."
    return None


def _ensure_active_device(response_lang: str = "en") -> str | None:
    """Return error message if no device can be activated, else None."""
    import auth.spotify as sa
    import time
    for attempt in range(2):
        resp = sa.request("GET", "/me/player/devices")
        if resp.status_code != 200:
            return "Keine Spotify-Geräte gefunden." if response_lang == "de" else "No Spotify devices found."
        devices = resp.json().get("devices", [])
        if not devices:
            if attempt < 1:
                time.sleep(1.0)
                continue
            return "Spotify läuft auf keinem Gerät. Bitte Spotify öffnen." if response_lang == "de" else "Spotify is not running on any device. Please open Spotify."
        active = next((d for d in devices if d.get("is_active")), None)
        if not active:
            preferred = (
                next((d for d in devices if d.get("type") == "Computer"), None)
                or devices[0]
            )
            sa.request("PUT", "/me/player", json={"device_ids": [preferred["id"]], "play": False})
            time.sleep(0.5)
        return None
    return "Kein aktives Spotify-Gerät gefunden." if response_lang == "de" else "No active Spotify device found."


def query_spotify(target: str, response_lang: str = "en") -> dict:
    import auth.spotify as sa
    err = _spotify_check(response_lang)
    if err:
        return {"success": False, "message": err}
    try:
        resp = sa.request("GET", "/me/player/currently-playing")
        if resp.status_code == 204:
            msg = "Gerade nichts aktiv in Spotify." if response_lang == "de" else "Nothing is currently active in Spotify."
            return {"success": True, "message": msg}
        data = resp.json()
        item = data.get("item") or {}
        name = item.get("name", "?")
        artists = ", ".join(a["name"] for a in item.get("artists", []))
        icon = "♪" if data.get("is_playing") else "⏸"
        return {"success": True, "message": f"{icon} {name} — {artists}"}
    except Exception as e:
        msg = f"Spotify-Fehler: {e}" if response_lang == "de" else f"Spotify error: {e}"
        return {"success": False, "message": msg}


def control_spotify(target: str, query: str | None = None, response_lang: str = "en") -> dict:
    import auth.spotify as sa
    err = _spotify_check(response_lang)
    if err:
        return {"success": False, "message": err}
    try:
        device_err = _ensure_active_device(response_lang)
        if device_err:
            return {"success": False, "message": device_err}

        if target == "search_track":
            resp = sa.request("GET", "/search", params={"q": query, "type": "track", "limit": 1})
            resp.raise_for_status()
            tracks = resp.json().get("tracks", {}).get("items", [])
            if not tracks:
                msg = f"Kein Song gefunden für '{query}'." if response_lang == "de" else f"No song found for '{query}'."
                return {"success": False, "message": msg}
            t = tracks[0]
            play_resp = sa.request("PUT", "/me/player/play", json={"uris": [t["uri"]]})
            if play_resp.status_code not in (200, 202, 204):
                msg = f"Spotify-Fehler beim Abspielen: {play_resp.status_code}" if response_lang == "de" else f"Spotify play error: {play_resp.status_code}"
                return {"success": False, "message": msg}
            return {"success": True, "message": f"♪ {t['name']} — {t['artists'][0]['name']}"}

        if target == "search_playlist":
            resp = sa.request("GET", "/search", params={"q": query, "type": "playlist", "limit": 1})
            resp.raise_for_status()
            items = resp.json().get("playlists", {}).get("items", [])
            if not items:
                msg = f"Playlist '{query}' nicht gefunden." if response_lang == "de" else f"Playlist '{query}' not found."
                return {"success": False, "message": msg}
            pl = items[0]
            play_resp = sa.request("PUT", "/me/player/play", json={"context_uri": pl["uri"]})
            if play_resp.status_code not in (200, 202, 204):
                msg = f"Spotify-Fehler beim Abspielen: {play_resp.status_code}" if response_lang == "de" else f"Spotify play error: {play_resp.status_code}"
                return {"success": False, "message": msg}
            return {"success": True, "message": f"▶ Playlist: {pl['name']}"}

        if target == "search_artist":
            resp = sa.request("GET", "/search", params={"q": query, "type": "artist", "limit": 1})
            resp.raise_for_status()
            artists = resp.json().get("artists", {}).get("items", [])
            if not artists:
                msg = f"Künstler '{query}' nicht gefunden." if response_lang == "de" else f"Artist '{query}' not found."
                return {"success": False, "message": msg}
            a = artists[0]
            play_resp = sa.request("PUT", "/me/player/play", json={"context_uri": a["uri"]})
            if play_resp.status_code not in (200, 202, 204):
                msg = f"Spotify-Fehler beim Abspielen: {play_resp.status_code}" if response_lang == "de" else f"Spotify play error: {play_resp.status_code}"
                return {"success": False, "message": msg}
            return {"success": True, "message": f"♪ {a['name']}"}

    except Exception as e:
        msg = f"Spotify-Fehler: {e}" if response_lang == "de" else f"Spotify error: {e}"
        return {"success": False, "message": msg}

    msg = f"Spotify-Aktion '{target}' wird nicht unterstützt." if response_lang == "de" else f"Spotify action '{target}' is not supported."
    return {"success": False, "message": msg}


def execute(parsed: dict) -> dict | None:
    action = parsed.get("action")
    target = parsed.get("target")
    response_lang = lang(parsed)
    if action == "query_spotify":
        return query_spotify(target, response_lang)
    if action == "control_spotify":
        return control_spotify(target, parsed.get("query"), response_lang)
    return None
