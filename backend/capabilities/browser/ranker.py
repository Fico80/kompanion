import re
from urllib.parse import urlparse

from shared.llm import llm_complete

from .search import SearchResult


_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_TOKEN_RE = re.compile(r"[a-z0-9äöüß]+", re.IGNORECASE)
_NUMBER_RE = re.compile(r"(?<!\d)\d+(?!\d)")

_STOPWORDS = {
    "zeige", "zeig", "mir", "bitte", "please", "finde", "suche", "nach", "show", "find",
    "search", "open", "öffne", "info", "infos", "information", "informationen", "page",
    "seite", "website", "webseite", "über", "about", "for", "auf", "on", "bei",
    "für", "ein", "eine", "einen", "einer", "der", "die", "das", "den", "dem",
}

_TRANSLATION_HINTS = {
    "anleitung": {"guide", "tutorial"},
    "vergleich": {"compare", "comparison"},
    "preisvergleich": {"price", "comparison"},
    "handbuch": {"manual"},
    "dokumentation": {"docs", "documentation"},
    "lautsprecher": {"speaker"},
    "kopfhörer": {"headphones"},
}

_INTENT_KEYWORDS = {
    "wiki", "docs", "documentation", "github", "reddit", "download", "manual",
    "calculator", "calc", "price", "shop", "store", "forum", "release", "notes",
    "changelog", "api", "tutorial", "guide", "fandom", "archlinux", "arch",
    "anleitung", "walkthrough", "vergleich",
}

_COMMUNITY_PATHS = {"comment", "comments", "forum", "forums", "post", "posts", "tip", "tips"}
_COMMUNITY_TRIGGERS = {"reddit", "forum", "tip", "tipps", "community", "discussion"}
_VIDEO_TRIGGERS = {"video", "youtube", "yt", "anschauen", "watch", "clip"}
_TEXT_GUIDE_TRIGGERS = {"tutorial", "guide", "anleitung", "walkthrough", "howto", "how", "docs", "documentation"}
_TEXT_GUIDE_HINTS = {"wiki", "guide", "guides", "tutorial", "tutorials", "docs", "documentation", "manual", "walkthrough"}
_VIDEO_DOMAINS = {"youtube.com", "youtu.be", "tiktok.com", "instagram.com"}
_SHORT_VIDEO_DOMAINS = {"tiktok.com", "instagram.com"}
_MODEL_VARIANTS = {
    "pro", "max", "plus", "mini", "ultra", "lite", "se", "air", "edge", "fold",
    "promax", "pro-max", "xl",
}

# Minimum score to auto-open; below this, fall back to the search page.
MIN_CONFIDENCE = 8


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(text):
        token = raw.lower()
        if len(token) < 3 or token in _STOPWORDS:
            continue
        tokens.append(token)
        tokens.extend(sorted(_TRANSLATION_HINTS.get(token, set())))
    return tokens


def _numbers(text: str) -> list[str]:
    return _NUMBER_RE.findall(text)


def _intent_words(text: str) -> set[str]:
    words = {t.lower() for t in _TOKEN_RE.findall(text)}
    return words & _INTENT_KEYWORDS


def _domain_matches(netloc: str, domains: set[str]) -> bool:
    return any(netloc == domain or netloc.endswith("." + domain) for domain in domains)


def _matches_site_hint(netloc: str, hint: str) -> bool:
    if "." in hint:
        return netloc == hint or netloc.endswith("." + hint)
    return hint in netloc.split(".")


def _has_number(text: str, number: str) -> bool:
    return bool(re.search(rf"(?<!\d){re.escape(number)}(?!\d)", text))


def rank_results(
    task: str, query: str, site_hint: str | None, results: list[SearchResult]
) -> tuple[SearchResult | None, int]:
    if not results:
        return None, 0

    combined_input = f"{task} {query}"
    tokens = set(_tokens(combined_input))
    numbers = set(_numbers(combined_input))
    intent = _intent_words(combined_input)
    input_words = {t.lower() for t in _TOKEN_RE.findall(task)}
    wants_community = bool(_COMMUNITY_TRIGGERS & input_words)
    wants_video = bool(_VIDEO_TRIGGERS & input_words)
    wants_text_guide = bool(_TEXT_GUIDE_TRIGGERS & input_words) and not wants_video
    is_specific = len(tokens) + len(numbers) >= 3

    scored: list[tuple[int, SearchResult]] = []
    for result in results:
        hay_title = result.title.lower()
        hay_url = result.url.lower()
        hay_snippet = result.snippet.lower()
        combined = f"{hay_title} {hay_url} {hay_snippet}"
        score = 0

        # Domain hint
        parsed_url = urlparse(result.url)
        netloc = parsed_url.netloc.lower()
        if site_hint:
            hint = site_hint.lower()
            if _matches_site_hint(netloc, hint):
                score += 20
            elif hint in hay_title:
                score -= 5
            else:
                score -= 16

        # Entity and token matching
        for token in tokens:
            if token in hay_title:
                score += 4
            elif token in hay_url:
                score += 3
            elif token in hay_snippet:
                score += 1

        # Number matching for versions, levels, and model numbers
        for num in numbers:
            if _has_number(combined, num):
                score += 6
            elif re.search(rf"(?<!\d){re.escape(num)}\d+(?!\d)", combined):
                score -= 8

        # Intent keyword matching
        for word in intent:
            if word in hay_url or word in hay_title:
                score += 5

        # Product/model precision
        for variant in _MODEL_VARIANTS - tokens:
            if re.search(rf"(?<![a-z0-9]){re.escape(variant)}(?![a-z0-9])", combined):
                score -= 5

        # Specificity and homepage handling
        path_parts = [p for p in parsed_url.path.split("/") if p]
        if is_specific and not path_parts:
            score -= 30
        if not is_specific and len(path_parts) > 3:
            score -= 3

        # Community content
        if not wants_community:
            if any(p in _COMMUNITY_PATHS for p in path_parts):
                score -= 12

        # Tutorial defaults to text guides; video wins only when asked for.
        if wants_text_guide:
            if any(hint in hay_url or hint in hay_title for hint in _TEXT_GUIDE_HINTS):
                score += 8
            if _domain_matches(netloc, _SHORT_VIDEO_DOMAINS):
                score -= 14
            elif _domain_matches(netloc, _VIDEO_DOMAINS):
                score -= 14
        elif wants_video and _domain_matches(netloc, _VIDEO_DOMAINS):
            score += 8
            if _domain_matches(netloc, {"youtube.com", "youtu.be"}):
                score += 6
                if path_parts and path_parts[0] == "shorts":
                    score -= 6
            elif _domain_matches(netloc, _SHORT_VIDEO_DOMAINS):
                score -= 4

        scored.append((score, result))

    scored.sort(key=lambda x: -x[0])
    best_score, best_result = scored[0]
    return best_result, best_score


def llm_rank(task: str, query: str, site_hint: str | None, results: list[SearchResult]) -> SearchResult | None:
    if not results:
        return None

    lines = []
    for idx, result in enumerate(results, start=1):
        lines.append(
            f"{idx}. title: {result.title}\n"
            f"   url: {result.url}\n"
            f"   snippet: {result.snippet[:240]}"
        )

    prompt = f"""\
Pick the single best search result for the user's request.
Return ONLY the URL. If none fits, return NONE.

User request: {task}
Search query: {query}
Site hint: {site_hint or "(none)"}

Results:
{chr(10).join(lines)}
"""
    raw = llm_complete(prompt, max_tokens=80, temperature=0)
    if not raw:
        return None
    if raw.strip().upper().startswith("NONE"):
        return None
    match = _URL_RE.search(raw)
    if not match:
        return None
    chosen = match.group(0).rstrip(".,)")
    for result in results:
        if result.url.rstrip("/") == chosen.rstrip("/"):
            return result
    return None
