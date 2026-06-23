import re
from shared.i18n import detect_language


def parse_screen_vision(text: str) -> dict | None:
    stripped = text.strip()
    text_l = stripped.lower()

    if re.search(
        r"\b("
        r"was\s+(?:siehst|steht)|beschreib(?:e|en)?|lies|analysier(?:e|en)?|"
        r"what\s+(?:do\s+you\s+see|is\s+on)|describe|read|analy[sz]e"
        r")\b.{0,40}\b("
        r"bildschirm|screen|desktop|fenster|window|anzeige|screenshot"
        r")\b",
        text_l,
    ):
        return {
            "action": "screen_query",
            "target": stripped,
            "app_name": "Screen",
            "window_title": None,
            "window_class": None,
            "flatpak_id": None,
            "layout": None,
            "desktop": None,
            "monitor": None,
            "lang": detect_language(stripped),
        }

    return None
