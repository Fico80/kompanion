import os

from shared.i18n import lang

from .opener import open_url
from .query import build_search_query, clean_query, extract_direct_url, extract_site_hint, search_url
from .ranker import MIN_CONFIDENCE, llm_rank, rank_results
from .search import search_web


def execute_browser(parsed: dict) -> dict:
    task = parsed.get("task", "")
    response_lang = lang(parsed)
    action = parsed.get("action", "browser_find")

    direct_url = extract_direct_url(task)
    site_hint = extract_site_hint(task)
    query = build_search_query(task, site_hint)
    url = direct_url
    mode = "direct"

    if not url and action == "browser_search":
        url = search_url(query)
        mode = "search"

    if not url and action in ("browser_find", "browser_task"):
        results = search_web(query)
        use_llm = os.environ.get("BROWSER_LLM_RANKING", "0").strip().lower() not in {"0", "false", "no", "off"}
        chosen = None
        if use_llm:
            chosen = llm_rank(task, query, site_hint, results)
        if not chosen:
            chosen, confidence = rank_results(task, query, site_hint, results)
            if confidence < MIN_CONFIDENCE:
                chosen = None
        if chosen:
            url = chosen.url
            mode = "find"
        else:
            url = search_url(query)
            mode = "search_fallback"

    if not url:
        url = search_url(clean_query(task))
        mode = "search_fallback"

    print(f"[BROWSER] {action}: {query!r} -> {url} ({mode})")
    try:
        open_url(url)
    except Exception as e:
        msg = (f"Browser-Fehler: {e}" if response_lang == "de" else f"Browser error: {e}")
        return {"success": False, "message": msg}

    if response_lang == "de":
        msg = "Öffne passende Seite..." if mode == "find" else "Öffne Browser..."
    else:
        msg = "Opening matching page..." if mode == "find" else "Opening browser..."
    return {
        "success": True,
        "message": msg,
        "details": {"action": action, "query": query, "site_hint": site_hint, "url": url, "mode": mode},
    }
