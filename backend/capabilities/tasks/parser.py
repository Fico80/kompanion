import re

_TASK_WEEKDAYS = {
    "montag": 0, "monday": 0,
    "dienstag": 1, "tuesday": 1,
    "mittwoch": 2, "wednesday": 2,
    "donnerstag": 3, "thursday": 3,
    "freitag": 4, "friday": 4,
    "samstag": 5, "saturday": 5,
    "sonntag": 6, "sunday": 6,
}
_TASK_MONTHS = {
    "januar": 1, "january": 1,
    "februar": 2, "february": 2,
    "märz": 3, "march": 3,
    "april": 4,
    "mai": 5, "may": 5,
    "juni": 6, "june": 6,
    "juli": 7, "july": 7,
    "august": 8,
    "september": 9,
    "oktober": 10, "october": 10,
    "november": 11,
    "dezember": 12, "december": 12,
}


def _extract_due_date(text_lower: str):
    from datetime import datetime, timedelta, date as _date
    today = datetime.now().date()

    if re.search(r"\bübermorgen\b", text_lower):
        d = today + timedelta(days=2); return d.isoformat(), "übermorgen"
    if re.search(r"\bday\s+after\s+tomorrow\b", text_lower):
        d = today + timedelta(days=2); return d.isoformat(), "day after tomorrow"
    if re.search(r"\bmorgen\b", text_lower):
        d = today + timedelta(days=1); return d.isoformat(), "morgen"
    if re.search(r"\btomorrow\b", text_lower):
        d = today + timedelta(days=1); return d.isoformat(), "tomorrow"
    if re.search(r"\bheute\b", text_lower):
        return today.isoformat(), "heute"
    if re.search(r"\btoday\b", text_lower):
        return today.isoformat(), "today"

    m = re.search(r"\bin\s+(\d+)\s*(?:tag(?:en)?|days?)\b", text_lower)
    if m:
        d = today + timedelta(days=int(m.group(1))); return d.isoformat(), f"in {m.group(1)} days"
    if re.search(r"\bin\s+einer?\s+woche\b", text_lower):
        d = today + timedelta(days=7); return d.isoformat(), "in einer Woche"
    if re.search(r"\bin\s+(?:a\s+week|one\s+week)\b", text_lower):
        d = today + timedelta(days=7); return d.isoformat(), "in a week"

    next_week = bool(re.search(r"\b(nächste[rn]?\s+woche|next\s+week)\b", text_lower))
    for name, num in _TASK_WEEKDAYS.items():
        if re.search(r"\b(?:(?:am|on|next)\s+)?" + name + r"\b", text_lower):
            offset = (num - today.weekday()) % 7
            if offset == 0 or next_week:
                offset += 7
            d = today + timedelta(days=offset)
            return d.isoformat(), name.capitalize()

    dm = re.search(r"\b(?:am\s+|on\s+|bis\s+(?:zum\s+)?)(\d{1,2})(?:st|nd|rd|th)?\s*\.?\s*(?:of\s+)?(" + "|".join(_TASK_MONTHS) + r")?\b", text_lower)
    if dm:
        day, mon_name = int(dm.group(1)), dm.group(2)
        try:
            if mon_name:
                mo = _TASK_MONTHS[mon_name]
                d = _date(today.year, mo, day)
                if d < today:
                    d = _date(today.year + 1, mo, day)
            else:
                d = _date(today.year, today.month, day)
                if d < today:
                    mo = today.month % 12 + 1
                    y = today.year + (1 if today.month == 12 else 0)
                    d = _date(y, mo, day)
            return d.isoformat(), f"{day}."
        except ValueError:
            pass
    return None, None


def _clean_task_text(text_original: str) -> str:
    t = text_original
    t = re.sub(r"^\s*(?:to-?do|aufgabe|task)\s*[:\-]?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(erinnere?\s+(?:mich|mir)|remind\s+me\s+(?:to)?)\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(daran|dran)\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(heute|morgen|übermorgen|today|tomorrow|day\s+after\s+tomorrow)\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\bin\s+\d+\s*(?:tag(?:en)?|days?)\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\bin\s+(?:einer?\s+woche|a\s+week|one\s+week)\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(nächste[rn]?\s+woche|next\s+week)\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(?:(?:am|on|next)\s+)?(?:" + "|".join(_TASK_WEEKDAYS) + r")\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(?:(?:am|on|bis\s+zum)\s+)?\d{1,2}(?:st|nd|rd|th)?\s*\.?\s*(?:of\s+)?(?:" + "|".join(_TASK_MONTHS) + r")?\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(neue[rs]?|hinzufügen?|hinzu|füge?|trage?|eintragen?|ein|erstelle?n?|merke?|notiere?|add|create|new)\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(aufgabe[n]?|to-?do[s]?|task[s]?)\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(als|bitte|noch|dass|ich|soll(?:te)?|please|that|i|should)\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^\s*(?:an|um|bis|für|am|zum|zur|at|by|for|on|to)\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip(" ,.-")
    return t


def parse_task(text_lower: str, text_original: str) -> dict | None:
    has_task_word = bool(re.search(r"\b(aufgaben?|to-?dos?|tasks?)\b", text_lower))

    def _result(action, **extra):
        base = {"action": action, "app_name": "Aufgaben",
                "window_title": None, "window_class": None, "flatpak_id": None,
                "layout": None, "desktop": None, "monitor": None}
        base.update(extra)
        return base

    # 1. Query open tasks
    query_markers = re.search(
        r"\b(was|welche|zeig|zeige|anzeig\w*|liste|offen|offene|anstehend\w*|alle|meine|gibt'?s|hab(?:e)?\s+ich"
        r"|show|list|display|open|pending|all|my|what|do\s+i\s+have)\b",
        text_lower,
    )
    query_phrase = re.search(
        r"\bwas\b.{0,30}\b(erledigen|zu\s+tun|zu\s+erledigen)\b"
        r"|\bwhat\b.{0,30}\b(to\s+do|needs?\s+to\s+be\s+done|do\s+i\s+need\s+to)\b",
        text_lower,
    )
    if (has_task_word and query_markers and not re.search(r"\b(neue[rs]?|hinzu|füge?|erstelle?|trage?|erinnere?|add|create|remind)\b", text_lower)) or query_phrase:
        return _result("query_tasks", target="open")

    # 2. Complete a task
    complete_trigger = (
        re.search(r"\berledige\b", text_lower)
        or re.search(r"\b(erledigt|abgehakt|abgeschlossen|done|completed?|finished?|check(?:ed)?\s+off)\b", text_lower)
        or re.search(r"\bhake?\b.{0,30}\bab\b", text_lower)
        or re.search(r"\bmarkiere?\b.{0,30}\b(erledigt|fertig)\b", text_lower)
        or re.search(r"\bmark\b.{0,20}\b(as\s+done|as\s+complete[d]?|off)\b", text_lower)
        or (has_task_word and re.search(r"\b(fertig|gemacht|done|finished?)\b", text_lower))
    )
    if complete_trigger:
        im = (re.search(r"\b(?:aufgabe|task|to-?do|nummer|nr\.?|punkt|number)\s*(\d{1,2})\b", text_lower)
              or re.search(r"\b(\d{1,2})\b", text_lower))
        if im:
            return _result("complete_task", task_index=int(im.group(1)), target=im.group(1),
                           app_name="Aufgabe erledigt")
        ref = re.sub(r"\b(erledige|erledigt|abgehakt|abgeschlossen|hake?|ab|markiere?|als|fertig|gemacht"
                     r"|done|complete[d]?|finish(?:ed)?|check(?:ed)?\s+off|mark(?:ed)?|as|off|die|den|das|meine?|bitte|the|my|please)\b",
                     "", text_original, flags=re.IGNORECASE)
        ref = re.sub(r"\b(aufgabe[n]?|to-?do[s]?|task[s]?)\b", "", ref, flags=re.IGNORECASE)
        ref = re.sub(r"\s+", " ", ref).strip(" ,.-")
        return _result("complete_task", task_ref=ref, target=ref, app_name="Aufgabe erledigt")

    # 3. Create a task
    create_trigger = (
        re.search(r"^\s*(?:to-?do|aufgabe|task)\b", text_lower)
        or re.search(r"\b(neue[rs]?\s+(?:aufgabe|to-?do|task)|aufgabe\s+hinzu|merke?\s+als\s+aufgabe"
                     r"|add\s+(?:a\s+)?(?:task|to-?do)|create\s+(?:a\s+)?(?:task|to-?do)|new\s+task)\b", text_lower)
        or (has_task_word and re.search(r"\b(hinzufügen?|hinzu|füge?|trage?|eintragen?|erstelle?n?|notiere?|add|create)\b", text_lower))
        or re.search(r"\b(erinnere?\s+(?:mich|mir)|remind\s+me\b)", text_lower)
    )
    if create_trigger:
        due, due_label = _extract_due_date(text_lower)
        task_text = _clean_task_text(text_original)
        if not task_text:
            return None
        label = f"Task: {task_text}" + (f" (by {due_label})" if due_label else "")
        return _result("add_task", target=task_text, task_text=task_text,
                       task_due=due, task_due_label=due_label, app_name=label)

    return None
