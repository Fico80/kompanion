import base64
import mimetypes
import os
import shutil
import subprocess
import time
from pathlib import Path

import requests

from shared.i18n import lang
from shared.paths import DATA_DIR


def _vision_endpoint() -> str:
    raw = os.environ.get("VISION_BASE_URL", "").rstrip("/")
    if not raw:
        raw = os.environ.get("LLM_BASE_URL", "").rstrip("/")
    if raw.endswith("/chat/completions"):
        return raw
    return raw + "/chat/completions" if raw else ""


def _vision_key(endpoint: str) -> str:
    using_local = any(h in endpoint for h in ("localhost", "127.0.0.1", "::1", "0.0.0.0"))
    if using_local:
        return os.environ.get("VISION_API_KEY", "") or "local"
    return os.environ.get("VISION_API_KEY", "") or os.environ.get("LLM_API_KEY", "")


def _capture_screen() -> Path:
    if not shutil.which("grim"):
        raise RuntimeError("grim is not installed")

    out_dir = DATA_DIR / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"screen_{int(time.time())}.png"
    subprocess.run(["grim", str(path)], check=True, timeout=5)
    return path


def _image_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _ask_vision(question: str, image_path: Path, response_lang: str) -> str:
    endpoint = _vision_endpoint()
    if not endpoint:
        raise RuntimeError("VISION_BASE_URL or LLM_BASE_URL is not configured")

    model = os.environ.get("VISION_MODEL", os.environ.get("LLM_MODEL", "gpt-4o-mini"))
    key = _vision_key(endpoint)
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    instruction = (
        "Du bist die visuelle Bildschirmwahrnehmung eines lokalen KDE-Desktop-Assistenten. "
        "Beantworte die Frage kurz und konkret auf Deutsch. Wenn du etwas nicht sicher erkennen kannst, sag das."
        if response_lang == "de"
        else "You are the visual screen perception of a local KDE desktop assistant. "
             "Answer briefly and concretely in English. If you cannot confidently see something, say so."
    )
    prompt = question or ("Was ist auf dem Bildschirm zu sehen?" if response_lang == "de" else "What is on the screen?")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"{instruction}\n\nFrage/Question: {prompt}"},
                    {"type": "image_url", "image_url": {"url": _image_data_url(image_path)}},
                ],
            }
        ],
        "max_tokens": int(os.environ.get("VISION_MAX_TOKENS", "400")),
        "temperature": float(os.environ.get("VISION_TEMPERATURE", "0.1")),
    }

    resp = requests.post(endpoint, headers=headers, json=payload, timeout=int(os.environ.get("VISION_TIMEOUT", "60")))
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def execute(parsed: dict) -> dict:
    response_lang = lang(parsed)
    try:
        screenshot = _capture_screen()
        answer = _ask_vision(parsed.get("target") or "", screenshot, response_lang)
        return {"success": True, "message": answer, "details": {"screenshot": str(screenshot)}}
    except Exception as e:
        msg = (
            f"Bildschirm konnte nicht analysiert werden: {e}"
            if response_lang == "de"
            else f"Could not analyze the screen: {e}"
        )
        return {"success": False, "message": msg}
