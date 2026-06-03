from datetime import datetime, timedelta
from shared.i18n import lang


_DE_WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
_DE_MONTHS = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]
_DE_ORDINALS = {
    1: "erster",
    2: "zweiter",
    3: "dritter",
    4: "vierter",
    5: "fünfter",
    6: "sechster",
    7: "siebter",
    8: "achter",
    9: "neunter",
    10: "zehnter",
    11: "elfter",
    12: "zwölfter",
    13: "dreizehnter",
    14: "vierzehnter",
    15: "fünfzehnter",
    16: "sechzehnter",
    17: "siebzehnter",
    18: "achtzehnter",
    19: "neunzehnter",
    20: "zwanzigster",
    21: "einundzwanzigster",
    22: "zweiundzwanzigster",
    23: "dreiundzwanzigster",
    24: "vierundzwanzigster",
    25: "fünfundzwanzigster",
    26: "sechsundzwanzigster",
    27: "siebenundzwanzigster",
    28: "achtundzwanzigster",
    29: "neunundzwanzigster",
    30: "dreißigster",
    31: "einunddreißigster",
}
_EN_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_EN_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _de_date(dt) -> str:
    ordinal = _DE_ORDINALS.get(dt.day, f"{dt.day}.")
    return f"{_DE_WEEKDAYS[dt.weekday()]}, {ordinal} {_DE_MONTHS[dt.month - 1]}"


def _en_date(dt) -> str:
    return f"{_EN_WEEKDAYS[dt.weekday()]}, {_EN_MONTHS[dt.month - 1]} {dt.day}"


def _date_text(dt, response_lang: str) -> str:
    return _de_date(dt) if response_lang == "de" else _en_date(dt)


def create_calendar_event(event_name: str, event_date: str, event_hour: int, event_min: int, response_lang: str = "en") -> dict:
    import auth.google_calendar as gc

    if not gc.is_authenticated():
        msg = "Google Kalender nicht verbunden. Öffne http://127.0.0.1:8000/calendar/auth" if response_lang == "de" else "Google Calendar is not connected. Open http://127.0.0.1:8000/calendar/auth"
        return {"success": False, "message": msg}

    tz = datetime.now().astimezone().tzinfo
    start = datetime.fromisoformat(event_date).replace(hour=event_hour, minute=event_min, tzinfo=tz)
    end = start + timedelta(hours=1)

    event = {
        "summary": event_name,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }
    try:
        resp = gc.request("POST", "/calendars/primary/events", json=event)
        resp.raise_for_status()
        if response_lang == "de":
            date_str = f"{_de_date(start)} um {start.strftime('%H:%M')} Uhr"
            message = f"Termin erstellt: {event_name}, {date_str}."
        else:
            date_str = f"{_en_date(start)} at {start.strftime('%H:%M')}"
            message = f"Event created: {event_name}, {date_str}."
        return {"success": True, "message": message}
    except Exception as e:
        msg = f"Termin konnte nicht erstellt werden: {e}" if response_lang == "de" else f"Event could not be created: {e}"
        return {"success": False, "message": msg}


def query_calendar(time_range: str, response_lang: str = "en") -> dict:
    import auth.google_calendar as gc

    if not gc.is_authenticated():
        msg = "Google Kalender nicht verbunden. Öffne http://127.0.0.1:8000/calendar/auth im Browser." if response_lang == "de" else "Google Calendar is not connected. Open http://127.0.0.1:8000/calendar/auth in your browser."
        return {"success": False, "message": msg}

    tz = datetime.now().astimezone().tzinfo
    today_local = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)

    if time_range == "tomorrow":
        time_min = today_local + timedelta(days=1)
        time_max = today_local + timedelta(days=2)
        label = "morgen" if response_lang == "de" else "tomorrow"
    elif time_range == "day_after_tomorrow":
        time_min = today_local + timedelta(days=2)
        time_max = today_local + timedelta(days=3)
        label = "übermorgen" if response_lang == "de" else "the day after tomorrow"
    elif time_range == "week":
        time_min = today_local
        time_max = today_local + timedelta(days=7)
        label = "diese Woche" if response_lang == "de" else "this week"
    elif time_range == "next_week":
        days_until_monday = (7 - today_local.weekday()) % 7 or 7
        time_min = today_local + timedelta(days=days_until_monday)
        time_max = time_min + timedelta(days=7)
        label = "nächste Woche" if response_lang == "de" else "next week"
    elif time_range == "next":
        time_min = datetime.now(tz)
        time_max = time_min + timedelta(days=30)
        label = "nächster" if response_lang == "de" else "next"
    else:
        time_min = today_local
        time_max = today_local + timedelta(days=1)
        label = "heute" if response_lang == "de" else "today"

    try:
        resp = gc.request(
            "GET",
            "/calendars/primary/events",
            params={
                "timeMin": time_min.isoformat(),
                "timeMax": time_max.isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": 1 if time_range == "next" else 15,
            },
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])

        if not items:
            msg = f"Keine Termine {label}." if response_lang == "de" else f"No events {label}."
            return {"success": True, "message": msg}

        multi_day = time_range in ("week", "next_week")
        lines = []
        for ev in items:
            start = ev.get("start", {})
            dt_str = start.get("dateTime") or start.get("date", "")
            summary = ev.get("summary", "Ohne Titel")
            if "T" in dt_str:
                dt = datetime.fromisoformat(dt_str)
                time_str = dt.strftime("%H:%M")
                prefix = _date_text(dt, response_lang) + " " if multi_day else ""
                lines.append(f"{prefix}{time_str} — {summary}")
            else:
                from datetime import date as _date

                d = _date.fromisoformat(dt_str)
                prefix = _date_text(d, response_lang) + " " if multi_day else ""
                all_day = "ganztägig" if response_lang == "de" else "all day"
                lines.append(f"{prefix}{summary} ({all_day})")

        if time_range == "next":
            msg = f"Nächster Termin: {lines[0]}" if response_lang == "de" else f"Next event: {lines[0]}"
            return {"success": True, "message": msg}

        count = len(lines)
        header = f"{count} Termin{'e' if count != 1 else ''} {label}:" if response_lang == "de" else f"{count} event{'s' if count != 1 else ''} {label}:"
        return {"success": True, "message": header + "\n" + "\n".join(lines)}

    except Exception as e:
        msg = f"Kalender-Fehler: {e}" if response_lang == "de" else f"Calendar error: {e}"
        return {"success": False, "message": msg}


def execute(parsed: dict) -> dict | None:
    action = parsed.get("action")
    response_lang = lang(parsed)
    if action == "create_calendar_event":
        return create_calendar_event(
            parsed.get("event_name", "Termin" if response_lang == "de" else "Event"),
            parsed.get("event_date", ""),
            parsed.get("event_hour", 9),
            parsed.get("event_min", 0),
            response_lang,
        )
    if action == "query_calendar":
        return query_calendar(parsed.get("calendar_time_range", "today"), response_lang)
    return None
