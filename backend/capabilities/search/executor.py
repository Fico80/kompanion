import os
import subprocess
from pathlib import Path
from shared.i18n import lang
from shared.paths import NOTES_DIR


_ORDINAL_DE = ["erste", "zweite", "dritte", "vierte", "fünfte"]
_ORDINAL_EN = ["first", "second", "third", "fourth", "fifth"]


def search_files(target: str | None, file_patterns: list | None,
                 time_filter: str | None, search_dir: str,
                 search_type: str | None = None, response_lang: str = "en") -> dict:
    time_args = {"today": 1, "yesterday": 2, "week": 7, "month": 30}
    mtime = time_args.get(time_filter)
    type_flag = {"directory": ["-type", "d"], "file": ["-type", "f"]}.get(search_type, [])

    found = []
    if search_type == "directory" and target:
        cmd = ["find", search_dir, "-maxdepth", "6"] + type_flag + ["-iname", f"*{target}*"]
        if mtime:
            cmd += ["-mtime", f"-{mtime}"]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=8).stdout
            found.extend(p for p in out.strip().splitlines() if p)
        except Exception:
            pass
    elif file_patterns:
        for pat in file_patterns:
            cmd = ["find", search_dir, "-maxdepth", "6"] + type_flag + ["-iname", pat]
            if mtime:
                cmd += ["-mtime", f"-{mtime}"]
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=8).stdout
                found.extend(p for p in out.strip().splitlines() if p)
            except Exception:
                pass
    elif target:
        cmd = ["find", search_dir, "-maxdepth", "6"] + type_flag + ["-iname", f"*{target}*"]
        if mtime:
            cmd += ["-mtime", f"-{mtime}"]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=8).stdout
            found.extend(p for p in out.strip().splitlines() if p)
        except Exception:
            pass

    found = sorted(set(p for p in found if "/." not in p))

    if not found:
        kind = ("Ordner" if search_type == "directory" else "Dateien") if response_lang == "de" else ("folders" if search_type == "directory" else "files")
        msg = f"Keine {kind} gefunden." if response_lang == "de" else f"No {kind} found."
        return {"success": False, "message": msg}

    if len(found) == 1:
        if os.path.isdir(found[0]):
            subprocess.Popen(["dolphin", "--new-window", found[0]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["xdg-open", found[0]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        name = os.path.basename(found[0])
        msg = f"Gefunden: {name}" if response_lang == "de" else f"Found: {name}"
        return {"success": True, "message": msg, "details": {"files": found}}

    top = found[:5]
    ordinals = _ORDINAL_DE if response_lang == "de" else _ORDINAL_EN
    numbered = ", ".join(
        f"{ordinals[i]}: {os.path.splitext(os.path.basename(p))[0].replace('_', ' ')}"
        for i, p in enumerate(top)
    )
    suffix = (f" (+{len(found) - 5} weitere)" if response_lang == "de" else f" (+{len(found) - 5} more)") if len(found) > 5 else ""
    msg = (
        f"{len(found)} gefunden — {numbered}{suffix}. Welche soll ich öffnen?"
        if response_lang == "de"
        else f"{len(found)} found — {numbered}{suffix}. Which one should I open?"
    )
    return {
        "success": True,
        "message": msg,
        "pending_selection": top,
        "details": {"files": found},
    }


def delete_file(path: str, response_lang: str = "en") -> dict:
    try:
        target = Path(path).resolve()
        notes_root = Path(NOTES_DIR).resolve()
        if not str(target).startswith(str(notes_root) + os.sep):
            msg = "Nur Notizen dürfen gelöscht werden." if response_lang == "de" else "Only notes may be deleted."
            return {"success": False, "message": msg}
        if target.exists():
            target.unlink()
            msg = f"Notiz gelöscht: {target.name}" if response_lang == "de" else f"Note deleted: {target.name}"
            return {"success": True, "message": msg}
        msg = "Datei nicht gefunden." if response_lang == "de" else "File not found."
        return {"success": False, "message": msg}
    except Exception as e:
        msg = f"Fehler beim Löschen: {e}" if response_lang == "de" else f"Error deleting file: {e}"
        return {"success": False, "message": msg}


def execute(parsed: dict) -> dict | None:
    action = parsed.get("action")
    response_lang = lang(parsed)
    if action == "search_files":
        return search_files(
            target=parsed.get("target"),
            file_patterns=parsed.get("file_patterns"),
            time_filter=parsed.get("time_filter"),
            search_dir=parsed.get("search_dir", os.path.expanduser("~")),
            search_type=parsed.get("search_type"),
            response_lang=response_lang,
        )
    if action == "delete_file":
        return delete_file(parsed.get("target") or "", response_lang)
    return None
