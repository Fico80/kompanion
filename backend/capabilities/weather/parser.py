import re


def parse_weather_query(text_lower: str, text_original: str) -> dict | None:
    primary = r"\b(wetter|weather|regen|regnen|regnet|regnerisch|schnee|schneit|schnein|sonnig|bewölkt|nebel|gewitter|forecast|vorhersage|klima|wettervorhersage|wetterbericht|rain|snow|sunny|cloudy|foggy|stormy)\b"
    secondary = r"(temperatur|temperature|windstärke|windgeschwindigkeit|luftfeuchtigkeit|niederschlag)"
    standalone = r"\b(grad|celsius|fahrenheit|wind|warm|kalt|heiß|draußen)\b"

    if not (
        re.search(primary, text_lower)
        or re.search(secondary, text_lower)
        or re.search(standalone, text_lower)
    ):
        return None

    aspect = None
    if re.search(r"\b(maximal|höchst|maximum|max)\b|maximaltemperatur", text_lower):
        aspect = "max_temp"
    elif re.search(r"\b(minimal|tief|mindest|minimum|min)\b|minimaltemperatur", text_lower):
        aspect = "min_temp"
    elif re.search(r"(temperatur|temperature|grad|celsius|fahrenheit|warm|kalt|heiß)", text_lower):
        aspect = "temperature"
    elif re.search(r"(windstärke|windgeschwindigkeit|\bwind\b)", text_lower):
        aspect = "wind"
    elif re.search(r"(luftfeuchtigkeit|feuchtigkeit|humidity)", text_lower):
        aspect = "humidity"
    elif re.search(r"\b(regen|regnen|regnet|regnerisch|niederschlag|rain)\b", text_lower):
        aspect = "rain"
    elif re.search(r"\b(schnee|snow)\b", text_lower):
        aspect = "snow"

    if re.search(r"\b(übermorgen|day\s+after\s+tomorrow)\b", text_lower):
        day = "day_after_tomorrow"
    elif re.search(r"\b(morgen|tomorrow)\b", text_lower):
        day = "tomorrow"
    else:
        day = "today"

    city = None
    m = re.search(r"\b(?:in|für|at|for)\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s[A-ZÄÖÜ][a-zäöüß]+)?)", text_original)
    if m:
        city = m.group(1)

    return {
        "action": "query_weather",
        "target": city,
        "app_name": "Weather",
        "weather_aspect": aspect,
        "weather_day": day,
        "window_title": None,
        "window_class": None,
        "flatpak_id": None,
        "layout": None,
        "desktop": None,
        "monitor": None,
    }
