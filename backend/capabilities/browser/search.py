from dataclasses import dataclass


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""


def search_web(query: str, max_results: int = 8) -> list[SearchResult]:
    try:
        from ddgs import DDGS
    except Exception as e:
        print(f"[BROWSER] ddgs unavailable: {e}")
        return []

    try:
        with DDGS() as ddgs:
            raw_results = list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        print(f"[BROWSER] search failed: {e}")
        return []

    results: list[SearchResult] = []
    for item in raw_results:
        url = item.get("href") or item.get("url") or ""
        title = item.get("title") or ""
        snippet = item.get("body") or item.get("snippet") or ""
        if url and title:
            results.append(SearchResult(title=title, url=url, snippet=snippet))
    return results
