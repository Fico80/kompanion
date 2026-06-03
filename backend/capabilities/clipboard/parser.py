import re


_CLIPBOARD_TASKS = [
    (re.compile(r"\bübersetze?\s+(?:das|den\s+text|es)?\s*auf\s+(.+)", re.I), "translate_to"),
    (re.compile(r"\bübersetze?\s+(?:das|den\s+text|es)?\s*ins?\s+(.+)", re.I), "translate_to"),
    (re.compile(r"\btranslate\s+(?:this|it|the\s+text)?\s*to\s+(.+)", re.I), "translate_to"),
    (re.compile(r"\btranslate\s+(?:this|it|the\s+text)?\s*into\s+(.+)", re.I), "translate_to"),
    (re.compile(r"\bübersetze?\s+(?:das|den\s+text|es)\b", re.I), "translate"),
    (re.compile(r"\btranslate\s+(?:this|it|the\s+text)\b", re.I), "translate"),
    (re.compile(r"\bfasse?\s+(?:das|den\s+text|es|zusammen)\b", re.I), "summarize"),
    (re.compile(r"\bzusammenfassung\b", re.I), "summarize"),
    (re.compile(r"\bsummariz[e]?\s+(?:this|it|the\s+text)\b", re.I), "summarize"),
    (re.compile(r"\bgive\s+me\s+a\s+summary\b", re.I), "summarize"),
    (re.compile(r"\berkl[äa]re?\s+(?:das|den\s+text|es|mir)\b", re.I), "explain"),
    (re.compile(r"\bwas\s+bedeutet\s+(?:das|es)\b", re.I), "explain"),
    (re.compile(r"\bexplain\s+(?:this|it|the\s+text)\b", re.I), "explain"),
    (re.compile(r"\bwhat\s+does\s+(?:this|it)\s+mean\b", re.I), "explain"),
    (re.compile(r"\bverbessere?\s+(?:das|den\s+text|es)\b", re.I), "improve"),
    (re.compile(r"\bkorrigiere?\s+(?:das|den\s+text|es)\b", re.I), "improve"),
    (re.compile(r"\bimprove\s+(?:this|it|the\s+text)\b", re.I), "improve"),
    (re.compile(r"\bfix\s+(?:this|it|the\s+text)\b", re.I), "improve"),
    (re.compile(r"\brewrite\s+(?:this|it|the\s+text)\b", re.I), "improve"),
]


def parse_clipboard(text: str) -> dict | None:
    text_s = text.strip()
    for pattern, task in _CLIPBOARD_TASKS:
        m = pattern.search(text_s)
        if m:
            lang = m.group(1).strip() if task == "translate_to" and m.lastindex >= 1 else None
            return {
                "action": "clipboard_task",
                "target": task,
                "clipboard_lang": lang,
                "app_name": "Zwischenablage",
                "window_title": None,
                "window_class": None,
                "flatpak_id": None,
                "layout": None,
                "desktop": None,
                "monitor": None,
            }
    return None
