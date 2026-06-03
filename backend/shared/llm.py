import os

import requests


def llm_complete(prompt: str, max_tokens: int = 450, temperature: float = 0.3) -> str | None:
    _raw = os.environ.get("LLM_BASE_URL", "").rstrip("/")
    if not _raw:
        return None
    base_url = _raw if _raw.endswith("/chat/completions") else _raw + "/chat/completions"
    key = os.environ.get("LLM_API_KEY", "")
    using_local = any(h in base_url for h in ("localhost", "127.0.0.1", "::1", "0.0.0.0"))
    if not key and not using_local:
        return None
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        resp = requests.post(
            base_url,
            headers=headers,
            json={
                "model": os.environ.get("LLM_MODEL", "qwen2.5:7b"),
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[LLM] Error: {e}")
        return None
