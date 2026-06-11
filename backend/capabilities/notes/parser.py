import re


_NOTE_RE = re.compile(
    r"^(?:notiz|notiere|merke(?:\s+dir)?|schreib\s+auf"
    r"|(?:mach[et]?|erstell[et]?|leg\s+an)\s+(?:eine?\s+)?(?:notiz|note)"
    r"|(?:make|create|take|add)\s+a?\s+note"
    r"|note|remember|write\s+down|jot\s+down|note\s+that|save\s+(?:a\s+)?note)[:\s]+(.+)$",
    re.IGNORECASE | re.DOTALL,
)

# Broad trigger: just detect intent, LLM extracts note name + content
_APPEND_TRIGGER_RE = re.compile(
    r"^(?:ergänze|füge\b.+?\bhinzu|add\s+to\s+(?:my\s+)?note|append\s+to\s+(?:my\s+)?note)\b",
    re.IGNORECASE | re.DOTALL,
)


def parse_note(text: str) -> dict | None:
    if _APPEND_TRIGGER_RE.search(text.strip()):
        return {
            "action": "append_note",
            "note_query": "",   # LLM extracts note name + content in executor
            "target": text.strip(),
            "app_name": "Note",
            "window_title": None, "window_class": None, "flatpak_id": None,
            "layout": None, "desktop": None, "monitor": None,
        }
    m = _NOTE_RE.match(text.strip())
    if not m:
        return None
    content = m.group(1).strip()
    return {
        "action": "save_note",
        "target": content,
        "app_name": "Note",
        "window_title": None,
        "window_class": None,
        "flatpak_id": None,
        "layout": None,
        "desktop": None,
        "monitor": None,
    }


def _extract_note_scope(text_lower: str, text_original: str) -> tuple:
    time_filter = None
    if re.search(r"\b(letzte[rn]?\s+woche|letzten?\s+7\s+tage[n]?|vergangene[rn]?\s+woche|last\s+week|past\s+week)\b", text_lower):
        time_filter = "week"
    elif re.search(r"\b(letzte[rn]?\s+monat|letzten?\s+30\s+tage[n]?|vergangene[rn]?\s+monat|last\s+month|past\s+month)\b", text_lower):
        time_filter = "month"
    elif re.search(r"\b(gestern|yesterday)\b", text_lower):
        time_filter = "yesterday"
    elif re.search(r"\b(heute|today)\b", text_lower):
        time_filter = "today"

    topic = None
    tm = re.search(
        r"\b(?:zu|über|ueber|bezüglich|zum\s+thema|about|on|regarding|wegen|rund\s+um|nach)\s+(.+)$",
        text_original,
        re.IGNORECASE,
    )
    if tm:
        topic = tm.group(1).strip()
        topic = re.sub(
            r"\b(notiert|aufgeschrieben|geschrieben|festgehalten|gespeichert|"
            r"noted|written|saved|recorded|"
            r"zusammen(?:fassen|gefasst)?|aufgezeichnet)\b.*$",
            "",
            topic,
            flags=re.IGNORECASE,
        )
        topic = re.sub(r"\b(meine[rn]?|notizen?|my|notes?)\b", "", topic, flags=re.IGNORECASE)
        topic = topic.strip(" ?.,-")
    return (topic or None), time_filter


def parse_knowledge_query(text_lower: str, text_original: str) -> dict | None:
    note_word = re.search(
        r"\bnotiz(?:en)?\b|\baufzeichnung(?:en)?\b|\bnotes?\b|\baufgeschrieben\b|\bwritten\s+down\b",
        text_lower,
    )

    if note_word and re.search(r"\b(fasse?|zusammenfass\w*|fass\b|überblick|zusammenfassung|summarize|summary|overview)\b", text_lower):
        topic, time_filter = _extract_note_scope(text_lower, text_original)
        return {
            "action": "query_notes",
            "note_mode": "summarize",
            "target": topic,
            "time_filter": time_filter,
            "app_name": "Notizen-Zusammenfassung",
            "window_title": None,
            "window_class": None,
            "flatpak_id": None,
            "layout": None,
            "desktop": None,
            "monitor": None,
        }

    is_question = (
        re.search(r"\bwas\b.{0,45}\b(notiert|aufgeschrieben|geschrieben|festgehalten|gespeichert|aufgezeichnet)\b", text_lower)
        or re.search(r"\b(was\s+weiß\s+ich|what\s+do\s+i\s+know)\b", text_lower)
        or (
            note_word
            and re.search(r"\b(durchsuche?|such\w*|finde?|zeig\w*|in\s+meinen|was\s+steht|gibt'?s|hab(?:e)?\s+ich"
                          r"|search|find|show|look\s+for|what'?s\s+in|do\s+i\s+have)\b", text_lower)
        )
    )
    if is_question:
        topic, time_filter = _extract_note_scope(text_lower, text_original)
        return {
            "action": "query_notes",
            "note_mode": "search",
            "target": topic,
            "time_filter": time_filter,
            "app_name": "Notizen-Suche",
            "window_title": None,
            "window_class": None,
            "flatpak_id": None,
            "layout": None,
            "desktop": None,
            "monitor": None,
        }

    return None
