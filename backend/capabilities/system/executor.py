import psutil
from shared.i18n import lang


def query_system(target: str, response_lang: str = "en") -> dict:
    t = (target or "").lower()

    if t in ("ram", "speicher", "memory"):
        m = psutil.virtual_memory()
        used = m.used / 1e9
        total = m.total / 1e9
        pct = m.percent
        msg = f"RAM: {used:.1f} GB von {total:.1f} GB belegt ({pct:.0f}%)" if response_lang == "de" else f"RAM: {used:.1f} GB of {total:.1f} GB used ({pct:.0f}%)"
        return {"success": True, "message": msg}

    if t in ("cpu", "prozessor"):
        pct = psutil.cpu_percent(interval=0.5)
        freq = psutil.cpu_freq()
        freq_str = f" @ {freq.current:.0f} MHz" if freq else ""
        msg = f"CPU: {pct:.0f}% Auslastung{freq_str}" if response_lang == "de" else f"CPU: {pct:.0f}% usage{freq_str}"
        return {"success": True, "message": msg}

    if t in ("disk", "festplatte", "speicherplatz", "storage"):
        d = psutil.disk_usage("/")
        used = d.used / 1e9
        total = d.total / 1e9
        pct = d.percent
        msg = f"Festplatte: {used:.1f} GB von {total:.1f} GB belegt ({pct:.0f}%)" if response_lang == "de" else f"Disk: {used:.1f} GB of {total:.1f} GB used ({pct:.0f}%)"
        return {"success": True, "message": msg}

    if t in ("akku", "battery", "batterie"):
        bat = psutil.sensors_battery()
        if not bat:
            msg = "Kein Akku gefunden." if response_lang == "de" else "No battery found."
            return {"success": False, "message": msg}
        status = ("lädt" if bat.power_plugged else "entlädt") if response_lang == "de" else ("charging" if bat.power_plugged else "discharging")
        label = "Akku" if response_lang == "de" else "Battery"
        return {"success": True, "message": f"{label}: {bat.percent:.0f}% ({status})"}

    if t in ("prozesse", "processes", "top"):
        procs = sorted(
            psutil.process_iter(["name", "cpu_percent"]),
            key=lambda p: p.info["cpu_percent"] or 0,
            reverse=True,
        )[:5]
        lines = ", ".join(
            f"{p.info['name']} ({p.info['cpu_percent']:.0f}%)"
            for p in procs
            if p.info["cpu_percent"] is not None
        )
        label = "Top-Prozesse" if response_lang == "de" else "Top processes"
        return {"success": True, "message": f"{label}: {lines}"}

    # General / all
    m = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=0.5)
    d = psutil.disk_usage("/")
    return {
        "success": True,
        "message": (
            f"CPU: {cpu:.0f}%  |  "
            f"RAM: {m.used/1e9:.1f}/{m.total/1e9:.1f} GB ({m.percent:.0f}%)  |  "
            f"Disk: {d.used/1e9:.0f}/{d.total/1e9:.0f} GB ({d.percent:.0f}%)"
        ),
    }


def execute(parsed: dict) -> dict | None:
    if parsed.get("action") == "query_system":
        return query_system(parsed.get("target"), lang(parsed))
    return None
