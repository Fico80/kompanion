import re
from shared.i18n import detect_language

_OPEN_RE = re.compile(
    r"(?:"
    r"(?:geh|gehe|navigiere|go|navigate)\s+(?:zu|auf|to)\s+\S"
    r"|(?:öffne|open)\s+(?:https?://\S+|[a-z0-9-]+(?:\.[a-z0-9-]+)+\S*)"
    r")",
    re.IGNORECASE,
)

_SEARCH_RE = re.compile(
    r"(?:"
    r"(?:suche?\s+(?:nach\s+)?|search\s+(?:for\s+)?).+\s+(?:im\s+internet|online|im\s+web|on\s+the\s+(?:web|internet))"
    r")",
    re.IGNORECASE,
)

_FIND_RE = re.compile(
    r"(?:"
    r"zeige?\s+mir[,.]?\s+\S"
    r"|show\s+me\s+\S"
    r")",
    re.IGNORECASE,
)

# File/folder context keywords — if present with "show me / zeig mir", let file_search handle it
_FILE_CTX_RE = re.compile(
    r"\b(fotos?|bilder?|photos?|dokumente?|documents?|dateien?|files?|ordner|folder|downloads?|videos?|musik|music|screenshots?|pdf)\b",
    re.IGNORECASE,
)


def parse_browser(text: str) -> dict | None:
    stripped = text.strip()
    detected = detect_language(text)
    if _OPEN_RE.search(stripped):
        return {"action": "browser_open", "task": stripped, "lang": detected}
    if _SEARCH_RE.search(stripped):
        return {"action": "browser_search", "task": stripped, "lang": detected}
    if _FIND_RE.search(stripped):
        if _FILE_CTX_RE.search(stripped):
            return None
        return {"action": "browser_find", "task": stripped, "lang": detected}
    return None
