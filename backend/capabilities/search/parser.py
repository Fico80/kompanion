import re
import os
from shared.paths import NOTES_DIR


_SEARCH_TRIGGER = re.compile(
    r"^(?:such[e]?|find[e]?|wo\s+ist|zeig\s+mir|suche\s+nach"
    r"|search\s+(?:for\s+)?|find\s+|look\s+for\s+|where\s+is\s+|show\s+me\s+|locate\s+"
    r"|öffne\s+(?:den\s+|die\s+|das\s+)?(?:ordner|datei|folder|file)\s+"
    r"|open\s+(?:the\s+)?(?:folder|file)\s+)"
    r"(?:(?:die|das|den|alle?|meine?|einem?|the|my|a|an|all)\s+)?(.+)$",
    re.IGNORECASE,
)
_TIME_FILTERS = [
    (re.compile(r"\b(?:von\s+)?(?:heute|today)\b", re.I), "today"),
    (re.compile(r"\b(?:von\s+)?(?:gestern|yesterday)\b", re.I), "yesterday"),
    (re.compile(r"\b(?:von\s+)?(?:letzte[rn]?\s+woche|letzten?\s+7\s+tagen?|last\s+week|past\s+week)\b", re.I), "week"),
    (re.compile(r"\b(?:von\s+)?(?:letzten?\s+monat|letzten?\s+30\s+tagen?|last\s+month|past\s+month)\b", re.I), "month"),
]
_FILE_TYPES = {
    "pdf":          ["*.pdf"],
    "bild":         ["*.jpg", "*.jpeg", "*.png", "*.webp", "*.gif", "*.heic"],
    "foto":         ["*.jpg", "*.jpeg", "*.png", "*.webp", "*.heic"],
    "image":        ["*.jpg", "*.jpeg", "*.png", "*.webp", "*.gif", "*.heic"],
    "photo":        ["*.jpg", "*.jpeg", "*.png", "*.webp", "*.heic"],
    "picture":      ["*.jpg", "*.jpeg", "*.png", "*.webp", "*.heic"],
    "video":        ["*.mp4", "*.mkv", "*.avi", "*.mov", "*.webm"],
    "musik":        ["*.mp3", "*.flac", "*.wav", "*.ogg", "*.m4a"],
    "music":        ["*.mp3", "*.flac", "*.wav", "*.ogg", "*.m4a"],
    "audio":        ["*.mp3", "*.flac", "*.wav", "*.ogg", "*.m4a"],
    "dokument":     ["*.pdf", "*.doc", "*.docx", "*.odt", "*.txt"],
    "document":     ["*.pdf", "*.doc", "*.docx", "*.odt", "*.txt"],
    "tabelle":      ["*.xlsx", "*.ods", "*.csv"],
    "spreadsheet":  ["*.xlsx", "*.ods", "*.csv"],
    "präsentation": ["*.pptx", "*.odp", "*.key"],
    "presentation": ["*.pptx", "*.odp", "*.key"],
    "code":         ["*.py", "*.js", "*.ts", "*.html", "*.css", "*.sh"],
    "notiz":        ["*.md"],
    "note":         ["*.md"],
    "markdown":     ["*.md"],
    "zip":          ["*.zip", "*.tar.gz", "*.tar", "*.7z", "*.rar"],
    "archive":      ["*.zip", "*.tar.gz", "*.tar", "*.7z", "*.rar"],
}
_SEARCH_DIRS = {
    "downloads":  os.path.expanduser("~/Downloads"),
    "dokumente":  os.path.expanduser("~/Documents"),
    "documents":  os.path.expanduser("~/Documents"),
    "bilder":     os.path.expanduser("~/Pictures"),
    "pictures":   os.path.expanduser("~/Pictures"),
    "fotos":      os.path.expanduser("~/Pictures"),
    "photos":     os.path.expanduser("~/Pictures"),
    "videos":     os.path.expanduser("~/Videos"),
    "musik":      os.path.expanduser("~/Music"),
    "music":      os.path.expanduser("~/Music"),
    "desktop":    os.path.expanduser("~/Desktop"),
    "uni":        os.path.expanduser("~/UNI"),
    "notizen":    str(NOTES_DIR),
    "notes":      str(NOTES_DIR),
}


def parse_file_search(text: str) -> dict | None:
    m = _SEARCH_TRIGGER.match(text.strip())
    if not m:
        return None
    raw = m.group(1).strip().lower()

    trigger_lower = text.strip().lower()
    if re.search(r"\b(öffne|open)\b.{0,10}\b(ordner|folder)\b", trigger_lower):
        search_type = "directory"
    elif re.search(r"\b(öffne|open)\b.{0,10}\b(datei|file)\b", trigger_lower):
        search_type = "file"
    else:
        search_type = None

    time_filter = None
    for pattern, label in _TIME_FILTERS:
        if pattern.search(raw):
            raw = pattern.sub("", raw).strip()
            time_filter = label
            break

    if re.search(r"\b(ordner|folder|directory)\b", raw, re.I):
        search_type = "directory"
        raw = re.sub(r"\b(?:ordner|folder|directory)\b", "", raw, flags=re.I).strip()
    elif re.search(r"\b(datei|file)\b", raw, re.I):
        search_type = "file"
        raw = re.sub(r"\b(?:datei|file)\b", "", raw, flags=re.I).strip()

    file_patterns = None
    for keyword, patterns in _FILE_TYPES.items():
        if re.search(r"\b" + keyword + r"(?:er|en|e|s)?\b", raw, re.I):
            file_patterns = patterns
            raw = re.sub(r"\b" + keyword + r"(?:er|en|e|s)?\b", "", raw, flags=re.I).strip()
            break

    search_dir = os.path.expanduser("~")
    for keyword, path in _SEARCH_DIRS.items():
        if re.search(r"\b" + keyword + r"\b", raw, re.I):
            search_dir = path
            raw = re.sub(r"\b" + keyword + r"\b", "", raw, flags=re.I).strip()
            if path == str(NOTES_DIR) and file_patterns is None:
                file_patterns = ["*.md"]
            break

    raw = re.sub(
        r"\b(von|über|im|in|aus|auf|nach|der|die|das|den|dem|des|ein|eine|einen|einem|einer|mit|from|on|at|the|a|an|with)\b",
        "", raw, flags=re.I,
    ).strip(" ,.-")

    # "show me" without any file/folder context → let browser handle it
    if re.match(r"show\s+me\s+", text.strip(), re.IGNORECASE):
        if file_patterns is None and search_type is None and search_dir == os.path.expanduser("~"):
            return None

    # "open folder Downloads left" — only placement words remain → let _parse_regex open the folder
    _PLACEMENT_WORDS = {"left", "right", "full", "fullscreen", "links", "rechts", "vollbild", "maximized"}
    if search_type == "directory" and file_patterns is None and time_filter is None:
        remaining_words = set(raw.lower().split()) - _PLACEMENT_WORDS
        if not remaining_words:
            return None

    return {
        "action": "search_files",
        "target": raw or None,
        "file_patterns": file_patterns,
        "time_filter": time_filter,
        "search_dir": search_dir,
        "search_type": search_type,
        "app_name": "Dateisuche",
        "window_title": None, "window_class": None, "flatpak_id": None,
        "layout": None, "desktop": None, "monitor": None,
    }
