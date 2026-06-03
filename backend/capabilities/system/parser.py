import re


def parse_system_query(text_lower: str) -> dict | None:
    def _result(target, label):
        return {
            "action": "query_system",
            "target": target,
            "app_name": label,
            "window_title": None,
            "window_class": None,
            "flatpak_id": None,
            "layout": None,
            "desktop": None,
            "monitor": None,
        }

    if re.search(r"\b(ram|arbeitsspeicher|speicher|memory)\b", text_lower):
        return _result("ram", "RAM-Auslastung")
    if re.search(r"\b(cpu|prozessor|auslastung)\b", text_lower):
        return _result("cpu", "CPU-Auslastung")
    if re.search(r"\b(festplatte|disk|speicherplatz|storage|laufwerk)\b", text_lower):
        return _result("disk", "Festplatte")
    if re.search(r"\b(akku|batterie|battery|ladung)\b", text_lower):
        return _result("akku", "Akkustand")
    if re.search(r"\b(prozesse|processes|top.?prozesse)\b", text_lower):
        return _result("prozesse", "Prozesse")
    if re.search(r"\b(systeminfo|systemstatus|systemzustand|computerstatus)\b|\b(system|computer|pc)\b.{0,20}\b(status|info|zustand|auslastung)\b|\bwie\b.{0,20}\b(läuft|lädt|belegt|voll|frei)\b", text_lower):
        return _result("all", "Systeminfo")
    return None
