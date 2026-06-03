import os
import json
import time
import base64
import secrets
import tempfile
import requests
from urllib.parse import urlencode

REDIRECT_URI = "http://127.0.0.1:8000/spotify/callback"
SCOPES = " ".join([
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "playlist-read-private",
    "playlist-read-collaborative",
])
TOKEN_FILE = os.path.expanduser("~/.config/lokaler-assistent/spotify_tokens.json")

_pending_state: str | None = None


def _credentials() -> tuple[str, str]:
    return os.environ.get("SPOTIFY_CLIENT_ID", ""), os.environ.get("SPOTIFY_CLIENT_SECRET", "")


def _auth_header() -> str:
    cid, secret = _credentials()
    return "Basic " + base64.b64encode(f"{cid}:{secret}".encode()).decode()


def get_auth_url() -> str:
    global _pending_state
    cid, _ = _credentials()
    _pending_state = secrets.token_urlsafe(16)
    params = {
        "client_id": cid,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": _pending_state,
    }
    return "https://accounts.spotify.com/authorize?" + urlencode(params)


def verify_state(received: str) -> bool:
    """Consume and verify the pending OAuth state token. Returns False if missing or wrong."""
    global _pending_state
    expected = _pending_state
    _pending_state = None  # one-time use — consume regardless of outcome
    if expected is None:
        return False
    return secrets.compare_digest(expected, received)


def exchange_code(code: str) -> dict:
    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": _auth_header(), "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI},
        timeout=10,
    )
    resp.raise_for_status()
    tokens = resp.json()
    tokens["expires_at"] = time.time() + tokens.get("expires_in", 3600)
    _save(tokens)
    return tokens


def _save(tokens: dict):
    token_dir = os.path.dirname(TOKEN_FILE)
    os.makedirs(token_dir, mode=0o700, exist_ok=True)
    try:
        os.chmod(token_dir, 0o700)
    except OSError:
        pass
    # Write to a temp file in the same directory (mkstemp creates with 0o600),
    # then atomically replace the target so it is never world-readable.
    fd, tmp = tempfile.mkstemp(dir=token_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(tokens, f)
        os.replace(tmp, TOKEN_FILE)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load() -> dict | None:
    try:
        with open(TOKEN_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def _refresh(tokens: dict) -> dict:
    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": _auth_header(), "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]},
        timeout=10,
    )
    resp.raise_for_status()
    new = resp.json()
    new.setdefault("refresh_token", tokens["refresh_token"])
    new["expires_at"] = time.time() + new.get("expires_in", 3600)
    _save(new)
    return new


def get_token() -> str | None:
    tokens = _load()
    if not tokens:
        return None
    if time.time() > tokens.get("expires_at", 0) - 60:
        tokens = _refresh(tokens)
    return tokens.get("access_token")


def is_authenticated() -> bool:
    return _load() is not None


def request(method: str, endpoint: str, **kwargs) -> requests.Response:
    token = get_token()
    if not token:
        raise RuntimeError("Nicht authentifiziert.")
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    return requests.request(
        method,
        f"https://api.spotify.com/v1{endpoint}",
        headers=headers,
        timeout=8,
        **kwargs,
    )
