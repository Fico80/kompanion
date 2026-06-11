import re

_NUMBER_WORDS = {
    "ein": 1, "eine": 1, "einer": 1, "einen": 1, "eins": 1,
    "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "funf": 5,
    "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10,
    "elf": 11, "zwölf": 12, "zwoelf": 12, "twelve": 12,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11,
}
_NUMBER_PATTERN = r"\d+|" + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True))


def _parse_number(value: str) -> int:
    value = value.lower()
    if value.isdigit():
        return int(value)
    return _NUMBER_WORDS[value]


def _duration_seconds(amount: str, unit: str) -> int:
    n = _parse_number(amount)
    unit = unit.lower()
    if unit.startswith(("h", "st")):
        return n * 3600
    if unit.startswith("m"):
        return n * 60
    return n


def _is_duration_phrase(text: str) -> bool:
    return bool(re.fullmatch(
        rf"(?:{_NUMBER_PATTERN})\s*(?:minuten?|mins?|stunden?|hours?|sekunden?|secs?|minutes?|seconds?)",
        text.strip(),
        re.IGNORECASE,
    ))


def parse_timer(text_lower: str, text_original: str) -> dict | None:
    if not re.search(r"\b(erinnere?|remind\s+me|timer|alarm|wecker|erinnerung|set\s+a\s+timer|set\s+timer)\b", text_lower):
        return None

    duration = None
    m = re.search(rf"\bin\s+({_NUMBER_PATTERN})\s*(minuten?|minutes?|mins?|stunden?|hours?|sekunden?|seconds?|secs?)\b", text_lower)
    if m:
        duration = _duration_seconds(m.group(1), m.group(2))
    if not duration:
        m = re.search(rf"\bfor\s+({_NUMBER_PATTERN})\s*(minutes?|mins?|hours?|seconds?|secs?)\b", text_lower)
        if m:
            duration = _duration_seconds(m.group(1), m.group(2))
    if not duration:
        if re.search(r"\b(einer?\s+halben?\s+stunde|half\s+an?\s+hour|30\s+minutes?)\b", text_lower):
            duration = 1800
        elif re.search(r"\b(einer?\s+stunde|one\s+hour|an?\s+hour)\b", text_lower):
            duration = 3600
        elif re.search(r"\b(einer?\s+minute|one\s+minute|a\s+minute)\b", text_lower):
            duration = 60
    if not duration:
        m = re.search(rf"\btimer\s+(?:auf\s+)?({_NUMBER_PATTERN})\s*(minuten?|stunden?|sekunden?|minutes?|hours?|seconds?)\b", text_lower)
        if m:
            duration = _duration_seconds(m.group(1), m.group(2))

    if not duration:
        return None

    label = ""
    lm = re.search(rf"\b(?:wegen|für|an|dass|for|about|to)\s+(.+?)(?:\s+in\s+(?:{_NUMBER_PATTERN})|\s+for\s+(?:{_NUMBER_PATTERN})|\s*$)", text_original, re.IGNORECASE)
    if lm and not _is_duration_phrase(lm.group(1)):
        label = lm.group(1).strip()
    else:
        rest = re.sub(r"\b(erinnere?\s+(mich\s+)?|remind\s+me\s+|timer\s+|alarm\s+|set\s+(?:a\s+)?timer\s+)", "", text_original, flags=re.IGNORECASE)
        rest = re.sub(rf"\bin\s+(?:{_NUMBER_PATTERN})\s*\w+\b|\bfor\s+(?:{_NUMBER_PATTERN})\s*\w+\b", "", rest, flags=re.IGNORECASE)
        rest = re.sub(rf"^(?:{_NUMBER_PATTERN})\s*(?:minuten?|mins?|stunden?|hours?|sekunden?|secs?|minutes?|seconds?)\b", "", rest, flags=re.IGNORECASE)
        rest = re.sub(r"\bin\s+einer?\s+(halben?\s+)?(stunde|minute|sekunde)\b", "", rest, flags=re.IGNORECASE)
        rest = re.sub(r"\b(half\s+an?\s+hour|an?\s+hour|a\s+minute)\b", "", rest, flags=re.IGNORECASE)
        rest = re.sub(r"\b(mich|mir|bitte|me|please)\b", "", rest, flags=re.IGNORECASE)
        rest = re.sub(r"\s+", " ", rest).strip(" ,.")
        if len(rest) > 2:
            label = rest
    label = re.sub(r"^(?:ans?|an\s+(?:das|den|die)|zum|zur)\s+", "", label, flags=re.IGNORECASE).strip()

    mins = duration // 60
    label_str = f" — {label}" if label else ""
    return {
        "action": "set_timer",
        "target": str(duration),
        "app_name": f"Timer {mins}min{label_str}",
        "timer_label": label,
        "window_title": None,
        "window_class": None,
        "flatpak_id": None,
        "layout": None,
        "desktop": None,
        "monitor": None,
    }
