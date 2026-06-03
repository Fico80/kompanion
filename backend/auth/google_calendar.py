import os
import json
import time
import secrets
import tempfile
import requests
from urllib.parse import urlencode

REDIRECT_URI = "http://127.0.0.1:8000/calendar/callback"
SCOPES = " ".join([
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
])
TOKEN_FILE = os.path.expanduser("~/.config/kompanion/google_calendar_tokens.json")
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"

_pending_state: str | None = None
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE = "https://www.googleapis.com/calendar/v3"


def _credentials() -> tuple[str, str]:
    return os.environ.get("GOOGLE_CLIENT_ID", ""), os.environ.get("GOOGLE_CLIENT_SECRET", "")


def get_auth_url() -> str:
    global _pending_state
    cid, _ = _credentials()
    _pending_state = secrets.token_urlsafe(16)
    params = {
        "client_id": cid,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": _pending_state,
    }
    return AUTH_URL + "?" + urlencode(params)


def verify_state(received: str) -> bool:
    """Consume and verify the pending OAuth state token. Returns False if missing or wrong."""
    global _pending_state
    expected = _pending_state
    _pending_state = None  # one-time use — consume regardless of outcome
    if expected is None:
        return False
    return secrets.compare_digest(expected, received)


def exchange_code(code: str) -> dict:
    cid, secret = _credentials()
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": cid,
            "client_secret": secret,
        },
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
    cid, secret = _credentials()
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": cid,
            "client_secret": secret,
        },
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
        f"{API_BASE}{endpoint}",
        headers=headers,
        timeout=8,
        **kwargs,
    )
