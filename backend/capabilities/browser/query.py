import re
from urllib.parse import quote_plus


_DIRECT_URL_RE = re.compile(r"(?P<url>https?://\S+|[a-z0-9-]+(?:\.[a-z0-9-]+)+\S*)", re.IGNORECASE)

_PREFIX_RE = re.compile(
    r"^(?:"
    r"zeige?\s+mir\s+|zeig\s+mir\s+|finde\s+|such(?:e)?\s+(?:nach\s+)?|"
    r"öffne\s+(?:mir\s+)?|open\s+|show\s+me\s+|find\s+|search\s+(?:for\s+)?"
    r")",
    re.IGNORECASE,
)

_SITE_HINT_RE = re.compile(
    r"\b(?:auf|bei|on|at)\s+([a-z0-9][a-z0-9.-]*(?:\.[a-z]{2,})?)\b",
    re.IGNORECASE,
)

_FILLER_RE = re.compile(
    r"\b(?:"
    r"mir|bitte|please|die|der|das|den|dem|eine|einen|einer|ein|"
    r"seite|page|webseite|website|info\s+page|infoseite|informationen?|infos?"
    r")\b",
    re.IGNORECASE,
)


def normalize_url(raw: str) -> str:
    value = raw.strip().rstrip(".,)")
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    return value


def extract_direct_url(text: str) -> str | None:
    match = _DIRECT_URL_RE.search(text)
    if not match:
        return None
    return normalize_url(match.group("url"))


def extract_site_hint(text: str) -> str | None:
    match = _SITE_HINT_RE.search(text)
    if not match:
        return None
    hint = match.group(1).strip().lower().rstrip(".,)")
    if hint in {"dem", "der", "die", "das", "internet", "web", "browser"}:
        return None
    return hint


def clean_query(text: str) -> str:
    query = _PREFIX_RE.sub("", text.strip())
    query = _SITE_HINT_RE.sub("", query)
    query = re.sub(r"\b(?:im|in\s+the)\s+(?:internet|web|browser)\b", "", query, flags=re.IGNORECASE)
    query = _FILLER_RE.sub(" ", query)
    query = re.sub(r"\b(?:über|zu|about|for)\b", " ", query, flags=re.IGNORECASE)
    query = re.sub(r"\s+", " ", query).strip(" .,!?:;-")
    return query or text.strip()


def build_search_query(task: str, site_hint: str | None = None) -> str:
    query = clean_query(task)
    if site_hint:
        if "." in site_hint:
            return f"site:{site_hint} {query}".strip()
        return f"{query} {site_hint}".strip()
    return query


def search_url(query: str) -> str:
    return f"https://duckduckgo.com/?q={quote_plus(query)}"
