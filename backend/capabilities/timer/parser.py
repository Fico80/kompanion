import re


def parse_timer(text_lower: str, text_original: str) -> dict | None:
    if not re.search(r"\b(erinnere?|remind\s+me|timer|alarm|wecker|erinnerung|set\s+a\s+timer|set\s+timer)\b", text_lower):
        return None

    duration = None
    m = re.search(r"\bin\s+(\d+)\s*(minuten?|mins?|stunden?|hours?|sekunden?|secs?)\b", text_lower)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        duration = n * (3600 if unit.startswith(("h", "st")) else 60 if unit.startswith("m") else 1)
    if not duration:
        m = re.search(r"\bfor\s+(\d+)\s*(minutes?|mins?|hours?|seconds?|secs?)\b", text_lower)
        if m:
            n, unit = int(m.group(1)), m.group(2).lower()
            duration = n * (3600 if unit.startswith("h") else 60 if unit.startswith("m") else 1)
    if not duration:
        if re.search(r"\b(einer?\s+halben?\s+stunde|half\s+an?\s+hour|30\s+minutes?)\b", text_lower):
            duration = 1800
        elif re.search(r"\b(einer?\s+stunde|one\s+hour|an?\s+hour)\b", text_lower):
            duration = 3600
        elif re.search(r"\b(einer?\s+minute|one\s+minute|a\s+minute)\b", text_lower):
            duration = 60
    if not duration:
        m = re.search(r"\btimer\s+(\d+)\s*(minuten?|stunden?|sekunden?|minutes?|hours?|seconds?)\b", text_lower)
        if m:
            n, unit = int(m.group(1)), m.group(2).lower()
            duration = n * (3600 if unit.startswith(("st", "h")) else 60 if unit.startswith("m") else 1)

    if not duration:
        return None

    label = ""
    lm = re.search(r"\b(?:wegen|für|an|dass|for|about|to)\s+(.+?)(?:\s+in\s+\d|\s+for\s+\d|\s*$)", text_original, re.IGNORECASE)
    if lm:
        label = lm.group(1).strip()
    else:
        rest = re.sub(r"\b(erinnere?\s+(mich\s+)?|remind\s+me\s+|timer\s+|alarm\s+|set\s+a?\s+timer\s+)", "", text_original, flags=re.IGNORECASE)
        rest = re.sub(r"\bin\s+\d+\s*\w+\b|\bfor\s+\d+\s*\w+\b", "", rest, flags=re.IGNORECASE)
        rest = re.sub(r"\bin\s+einer?\s+(halben?\s+)?(stunde|minute|sekunde)\b", "", rest, flags=re.IGNORECASE)
        rest = re.sub(r"\b(half\s+an?\s+hour|an?\s+hour|a\s+minute)\b", "", rest, flags=re.IGNORECASE)
        rest = re.sub(r"\b(mich|mir|bitte|me|please)\b", "", rest, flags=re.IGNORECASE)
        rest = re.sub(r"\s+", " ", rest).strip(" ,.")
        if len(rest) > 2:
            label = rest

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
