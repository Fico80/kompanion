import subprocess

from shared.llm import llm_complete
from shared.i18n import lang as parsed_lang


def clipboard_task(task: str, lang: str | None, response_lang: str = "en") -> dict:
    try:
        content = subprocess.run(
            ["wl-paste", "--no-newline"],
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout.strip()
    except Exception:
        msg = "Zwischenablage konnte nicht gelesen werden." if response_lang == "de" else "Clipboard could not be read."
        return {"success": False, "message": msg}

    if not content:
        msg = "Zwischenablage ist leer." if response_lang == "de" else "Clipboard is empty."
        return {"success": False, "message": msg}

    if response_lang == "de":
        prompts = {
            "translate":    f"Übersetze den folgenden Text ins Deutsche. Antworte NUR mit der Übersetzung:\n\n{content}",
            "translate_to": f"Übersetze den folgenden Text auf {lang}. Antworte NUR mit der Übersetzung:\n\n{content}",
            "summarize":    f"Fasse den folgenden Text auf Deutsch in 2-3 Sätzen zusammen. Antworte NUR mit der Zusammenfassung:\n\n{content}",
            "explain":      f"Erkläre den folgenden Text auf Deutsch einfach und verständlich. Antworte NUR mit der Erklärung:\n\n{content}",
            "improve":      f"Verbessere den folgenden Text sprachlich und stilistisch. Antworte NUR mit dem verbesserten Text:\n\n{content}",
        }
    else:
        prompts = {
            "translate":    f"Translate the following text into English. Reply ONLY with the translation:\n\n{content}",
            "translate_to": f"Translate the following text into {lang}. Reply ONLY with the translation:\n\n{content}",
            "summarize":    f"Summarize the following text in English in 2-3 sentences. Reply ONLY with the summary:\n\n{content}",
            "explain":      f"Explain the following text in English simply and clearly. Reply ONLY with the explanation:\n\n{content}",
            "improve":      f"Improve the following text linguistically and stylistically in English. Reply ONLY with the improved text:\n\n{content}",
        }
    prompt = prompts.get(task, prompts["explain"])

    result = llm_complete(prompt, max_tokens=512)
    if result is None:
        msg = "Kein LLM API Key oder lokaler LLM konfiguriert." if response_lang == "de" else "No LLM API key or local LLM configured."
        return {"success": False, "message": msg}

    try:
        subprocess.run(["wl-copy"], input=result, text=True, timeout=3)
    except Exception:
        pass

    return {"success": True, "message": result, "details": {"original_length": len(content)}}


def execute(parsed: dict) -> dict | None:
    if parsed.get("action") == "clipboard_task":
        return clipboard_task(parsed.get("target") or "explain", parsed.get("clipboard_lang"), parsed_lang(parsed))
    return None
