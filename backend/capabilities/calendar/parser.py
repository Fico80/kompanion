import re
from datetime import datetime, timedelta, date as _date
from shared.i18n import detect_language


def parse_create_calendar(text_lower: str, text_original: str) -> dict | None:
    create_verb = r"\b(erstell[et]?|erstellen|hinzufügen?|anlegen?|eintragen?|neu(e[rns]?)?|create|add|schedule|set\s+up|book)\b"
    calendar_noun = r"\b(termin[e]?|event|appointment|kalendereintrag|meeting|call)\b"
    if not (re.search(create_verb, text_lower) and re.search(calendar_noun, text_lower)):
        return None

    today = datetime.now().date()
    weekdays = {
        "montag": 0, "monday": 0,
        "dienstag": 1, "tuesday": 1,
        "mittwoch": 2, "wednesday": 2,
        "donnerstag": 3, "thursday": 3,
        "freitag": 4, "friday": 4,
        "samstag": 5, "saturday": 5,
        "sonntag": 6, "sunday": 6,
    }
    months = {
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

    event_date = None
    if re.search(r"\b(übermorgen|day\s+after\s+tomorrow)\b", text_lower):
        event_date = today + timedelta(days=2)
    elif re.search(r"\b(morgen|tomorrow)\b", text_lower):
        event_date = today + timedelta(days=1)
    elif re.search(r"\b(heute|today)\b", text_lower):
        event_date = today
    if event_date is None:
        for day_name, day_num in weekdays.items():
            if re.search(r"\b" + day_name + r"\b", text_lower):
                event_date = today + timedelta(days=(day_num - today.weekday()) % 7 or 7)
                break
    if event_date is None:
        dm = re.search(r"\b(?:am\s+|on\s+)?(\d{1,2})(?:st|nd|rd|th)?\s*\.?\s*(?:of\s+)?(" + "|".join(months) + r")?\b", text_lower)
        if dm:
            day, mon_name = int(dm.group(1)), dm.group(2)
            try:
                if mon_name:
                    y, mo = today.year, months[mon_name]
                    d = _date(y, mo, day)
                    event_date = d if d >= today else _date(y + 1, mo, day)
                else:
                    d = _date(today.year, today.month, day)
                    if d < today:
                        mo = today.month % 12 + 1
                        y = today.year + (1 if today.month == 12 else 0)
                        d = _date(y, mo, day)
                    event_date = d
            except ValueError:
                pass

    if event_date is None:
        is_de = detect_language(text_original) == "de"
        name_hint = re.sub(
            r"\b(erstell[et]?|erstellen|hinzufügen|anlegen|eintragen|neu(?:e[rns]?)?|"
            r"create|add|schedule|set\s+up|book|"
            r"termin[e]?|event|appointment|kalendereintrag|meeting|call|"
            r"bitte|mir|einen?|neuen?|mach[et]?|please|me|a|an)\b",
            "",
            text_original,
            flags=re.IGNORECASE,
        )
        name_hint = re.sub(r"\s+", " ", name_hint).strip(" ,.")
        label = f"'{name_hint}'" if name_hint else "Event"
        return {
            "action": "needs_clarification",
            "clarification_type": "append",
            "original_command": text_original,
            "prompt": f"{label}: Wann und um welche Uhrzeit?" if is_de else f"{label}: When and at what time?",
            "app_name": "Termin" if is_de else "Event",
            "window_title": None, "window_class": None, "flatpak_id": None,
            "layout": None, "desktop": None, "monitor": None,
        }

    event_hour, event_min = None, 0
    word_nums = {
        "ein": 1, "one": 1,
        "zwei": 2, "two": 2,
        "drei": 3, "three": 3,
        "vier": 4, "four": 4,
        "fünf": 5, "five": 5,
        "sechs": 6, "six": 6,
        "sieben": 7, "seven": 7,
        "acht": 8, "eight": 8,
        "neun": 9, "nine": 9,
        "zehn": 10, "ten": 10,
        "elf": 11, "eleven": 11,
        "zwölf": 12, "twelve": 12,
    }
    hm = re.search(r"\bhalb\s+(\d{1,2}|" + "|".join(word_nums) + r")\b", text_lower)
    if hm:
        h_str = hm.group(1)
        h = word_nums.get(h_str, int(h_str) if h_str.isdigit() else None)
        if h:
            event_hour, event_min = h - 1, 30
    if event_hour is None:
        tm = (
            re.search(r"\bum\s+(\d{1,2})\s+uhr\s+(\d{2})\b", text_lower)
            or re.search(r"\bum\s+(\d{1,2}):(\d{2})\b", text_lower)
            or re.search(r"\bum\s+(\d{1,2})\s*uhr\b", text_lower)
            or re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", text_lower)
            or re.search(r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b", text_lower)
        )
        if tm:
            event_hour = int(tm.group(1))
            event_min = int(tm.group(2)) if tm.lastindex and tm.lastindex >= 2 and tm.group(2) and tm.group(2).isdigit() else 0
            meridiem = None
            if tm.lastindex:
                for idx in range(2, tm.lastindex + 1):
                    value = tm.group(idx)
                    if value and value.lower() in ("am", "pm"):
                        meridiem = value.lower()
                        break
            if meridiem == "pm" and event_hour < 12:
                event_hour += 12
            elif meridiem == "am" and event_hour == 12:
                event_hour = 0

    if event_hour is None:
        is_de = detect_language(text_original) == "de"
        return {
            "action": "needs_clarification",
            "clarification_type": "append",
            "original_command": text_original,
            "prompt": "Um welche Uhrzeit soll der Termin sein?" if is_de else "At what time should the event be?",
            "app_name": "Termin" if is_de else "Event",
            "window_title": None, "window_class": None, "flatpak_id": None,
            "layout": None, "desktop": None, "monitor": None,
        }

    name = text_original
    name = re.sub(r"\b(erstell[et]?|erstellen|hinzufügen|anlegen|eintragen|neu(e[rns]?)?|mach[et]?|create|add|schedule|set\s+up|book)\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\b(termin[e]?|event|appointment|kalendereintrag|meeting|call)\b", "", name, flags=re.IGNORECASE)
    name = re.sub(
        r"\bum\s+\d{1,2}(?:(?:\s+uhr\s+|:)\d{2}|\s*uhr)?\b"
        r"|\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b"
        r"|\b\d{1,2}:\d{2}\s*(?:am|pm)?\b",
        "",
        name,
        flags=re.IGNORECASE,
    )
    name = re.sub(r"\b(?:am\s+|on\s+)?\d{1,2}(?:st|nd|rd|th)?\s*\.?\s*(?:of\s+)?\w*\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\b(heute|morgen|übermorgen|today|tomorrow|day\s+after\s+tomorrow|" + "|".join(weekdays) + r")\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\bhalb\s+\w+\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\b(uhr|am|pm)\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\b(um|am|an|für|bitte|mir|einen?|at|on|for|please|me|a|an)\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+", " ", name).strip(" ,.")
    if not name:
        name = "Event"

    return {
        "action": "create_calendar_event",
        "target": name,
        "app_name": f"Termin: {name}" if detect_language(text_original) == "de" else f"Event: {name}",
        "event_name": name,
        "event_date": event_date.isoformat(),
        "event_hour": event_hour,
        "event_min": event_min,
        "window_title": None, "window_class": None, "flatpak_id": None,
        "layout": None, "desktop": None, "monitor": None,
    }


def parse_calendar_query(text_lower: str) -> dict | None:
    if re.search(r"\b(erstell[et]?|hinzufügen?|anlegen?|eintragen?|neuen?|create|add|schedule|book)\b", text_lower):
        return None

    primary = r"\b(termin[e]?|kalender|calendar|events?|veranstaltung|appointment|meeting|schedule)\b"
    schedule_phrase = (
        r"\bwas\b.{0,20}\b(ansteht|habe ich|steht an|plane ich|ist geplant|ist heute|ist morgen)\b"
        r"|\bwhat\b.{0,20}\b(do i have|is scheduled|is planned|is today|is tomorrow|coming up)\b"
    )

    if not (re.search(primary, text_lower) or re.search(schedule_phrase, text_lower)):
        return None

    time_range = "today"
    if re.search(r"\b(nächste[rn]?\s+woche|next\s+week)\b", text_lower):
        time_range = "next_week"
    elif re.search(r"\b(diese[rn]?\s+woche|diese\s+7\s+tage|nächsten\s+7\s+tage|this\s+week)\b", text_lower):
        time_range = "week"
    elif re.search(r"\b(übermorgen|day\s+after\s+tomorrow)\b", text_lower):
        time_range = "day_after_tomorrow"
    elif re.search(r"\b(morgen|tomorrow)\b", text_lower):
        time_range = "tomorrow"
    elif re.search(r"\b(nächste[rns]?|next|bevorstehend|upcoming)\b", text_lower):
        time_range = "next"

    return {
        "action": "query_calendar",
        "target": time_range,
        "app_name": "Kalender" if "kalender" in text_lower or "termin" in text_lower else "Calendar",
        "calendar_time_range": time_range,
        "window_title": None, "window_class": None, "flatpak_id": None,
        "layout": None, "desktop": None, "monitor": None,
    }
