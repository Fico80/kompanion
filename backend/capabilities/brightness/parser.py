import re
from shared.numbers import NUMBER_PATTERN, parse_number


def parse_brightness(text_lower: str) -> dict | None:
    if re.search(r"\bverschieb|\bschieb|\bbeweg|\bschick|\bmove\b", text_lower):
        return None

    has_kw = re.search(r"\b(helligkeit|brightness|bildschirmhelligkeit|monitorhelligkeit|displayhelligkeit|bildschirm)\b", text_lower)
    has_relative = re.search(r"\b(heller|brighter|dunkler|darker|brightness up|brightness down|erhöhe[n]?|reduziere[n]?|verringere[n]?|erhöhen|reduzieren|verringern)\b", text_lower)
    has_standalone = re.search(r"\b(heller|dunkler)\b", text_lower) and not re.search(r"\b(monitor|display)\b", text_lower)

    if not (has_kw or has_relative or has_standalone):
        return None

    monitor = None
    monitor_match = re.search(r"\b(linke[rnms]?|left|rechte[rnms]?|right)\s+(monitor|bildschirm|screen|display)\b", text_lower)
    if monitor_match:
        monitor = 0 if monitor_match.group(1).startswith("link") or monitor_match.group(1) == "left" else 1

    label = "Bildschirmhelligkeit" if monitor is None else ("Linker Monitor" if monitor == 0 else "Rechter Monitor")
    step_m = re.search(rf"\b({NUMBER_PATTERN})\s*(?:prozent|%)\b", text_lower)
    step = max(1, min(parse_number(step_m.group(1)), 100)) if step_m else 10

    if re.search(r"\b(heller|brighter|brightness up|erhöhe[n]?|erhoehe[n]?|rauf|mehr licht)\b", text_lower):
        return {
            "action": "set_brightness",
            "target": f"+{step}%",
            "app_name": f"Heller +{step}%",
            "window_title": None,
            "window_class": None,
            "flatpak_id": None,
            "layout": None,
            "desktop": None,
            "monitor": monitor,
        }

    if re.search(r"\b(dunkler|dünkler|darker|brightness down|reduziere[n]?|verringere[n]?|verringern|runter|weniger licht)\b", text_lower):
        return {
            "action": "set_brightness",
            "target": f"-{step}%",
            "app_name": f"Dunkler -{step}%",
            "window_title": None,
            "window_class": None,
            "flatpak_id": None,
            "layout": None,
            "desktop": None,
            "monitor": monitor,
        }

    val_m = (
        re.search(rf"\bauf\s+({NUMBER_PATTERN})\b", text_lower)
        or re.search(rf"\b({NUMBER_PATTERN})\s*(?:prozent|%)\b", text_lower)
        or re.search(rf"\b({NUMBER_PATTERN})\b", text_lower)
    )
    if val_m and has_kw:
        val = max(0, min(parse_number(val_m.group(1)), 100))
        return {
            "action": "set_brightness",
            "target": f"{val}%",
            "app_name": f"{label} {val}%",
            "window_title": None,
            "window_class": None,
            "flatpak_id": None,
            "layout": None,
            "desktop": None,
            "monitor": monitor,
        }

    return None
