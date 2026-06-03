from datetime import datetime, date as _date
from shared.i18n import lang

_DE_WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
_DE_MONTHS   = ["Januar", "Februar", "März", "April", "Mai", "Juni",
                 "Juli", "August", "September", "Oktober", "November", "Dezember"]


def _format_due(due: str | None, response_lang: str = "en") -> str:
    """'überfällig', 'heute', 'morgen', weekday name or date — for natural task listings."""
    if not due:
        return ""
    try:
        d = _date.fromisoformat(due)
    except ValueError:
        return ""
    today = datetime.now().date()
    delta = (d - today).days
    en_weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    en_months = ["January", "February", "March", "April", "May", "June",
                 "July", "August", "September", "October", "November", "December"]
    if delta < 0:
        return "überfällig" if response_lang == "de" else "overdue"
    if delta == 0:
        return "heute" if response_lang == "de" else "today"
    if delta == 1:
        return "morgen" if response_lang == "de" else "tomorrow"
    if delta < 7:
        return _DE_WEEKDAYS[d.weekday()] if response_lang == "de" else en_weekdays[d.weekday()]
    return f"{d.day}. {_DE_MONTHS[d.month - 1]}" if response_lang == "de" else f"{en_months[d.month - 1]} {d.day}"


def add_task(task_text: str, due: str | None, due_label: str | None, response_lang: str = "en") -> dict:
    import memory as _mem
    task_id = _mem.add_task(task_text, due)
    if response_lang == "de":
        suffix = f" (bis {due_label})" if due_label else ""
        message = f"Aufgabe notiert: {task_text}{suffix}"
    else:
        suffix = f" (by {due_label})" if due_label else ""
        message = f"Task saved: {task_text}{suffix}"
    return {"success": True, "message": message, "task_id": task_id}


def query_tasks(response_lang: str = "en") -> dict:
    import memory as _mem
    tasks = _mem.get_open_tasks()
    if not tasks:
        message = "Keine offenen Aufgaben. Alles erledigt!" if response_lang == "de" else "No open tasks. All done!"
        return {"success": True, "message": message}
    lines = []
    for i, t in enumerate(tasks, 1):
        due = _format_due(t.get("due"), response_lang)
        lines.append(f"{i}. {t['text']}" + (f" ({due})" if due else ""))
    count = len(tasks)
    header = f"{count} offene Aufgabe{'n' if count != 1 else ''}:" if response_lang == "de" else f"{count} open task{'s' if count != 1 else ''}:"
    return {"success": True, "message": header + "\n" + "\n".join(lines)}


def complete_task(parsed: dict) -> dict:
    import memory as _mem
    response_lang = lang(parsed)
    task = None
    if parsed.get("task_index") is not None:
        task = _mem.get_open_task_by_index(int(parsed["task_index"]))
        if task is None:
            msg = f"Keine Aufgabe Nummer {parsed['task_index']}." if response_lang == "de" else f"No task number {parsed['task_index']}."
            return {"success": False, "message": msg}
    else:
        ref = (parsed.get("task_ref") or "").strip()
        if not ref:
            msg = "Welche Aufgabe soll ich abhaken?" if response_lang == "de" else "Which task should I mark as done?"
            return {"success": False, "message": msg}
        task = _mem.find_open_task_by_text(ref)
        if task is None:
            msg = f"Keine offene Aufgabe gefunden für '{ref}'." if response_lang == "de" else f"No open task found for '{ref}'."
            return {"success": False, "message": msg}
    _mem.complete_task(task["id"])
    msg = f"Erledigt: {task['text']}" if response_lang == "de" else f"Done: {task['text']}"
    return {"success": True, "message": msg, "task_id": task["id"]}


def reopen_task(task_id: int, response_lang: str = "en") -> dict:
    import memory as _mem
    if _mem.reopen_task(int(task_id)):
        msg = "Aufgabe wieder offen." if response_lang == "de" else "Task reopened."
        return {"success": True, "message": msg}
    msg = "Aufgabe nicht gefunden." if response_lang == "de" else "Task not found."
    return {"success": False, "message": msg}


def delete_task(task_id: int, response_lang: str = "en") -> dict:
    import memory as _mem
    if _mem.delete_task(int(task_id)):
        msg = "Aufgabe entfernt." if response_lang == "de" else "Task removed."
        return {"success": True, "message": msg}
    msg = "Aufgabe nicht gefunden." if response_lang == "de" else "Task not found."
    return {"success": False, "message": msg}


def execute(parsed: dict) -> dict | None:
    """Handle task actions. Returns None if action not handled."""
    action = parsed.get("action")
    target = parsed.get("target")
    response_lang = lang(parsed)

    if action == "add_task":
        return add_task(parsed.get("task_text", target or ""), parsed.get("task_due"), parsed.get("task_due_label"), response_lang)

    if action == "query_tasks":
        return query_tasks(response_lang)

    if action == "complete_task":
        return complete_task(parsed)

    if action == "reopen_task":
        return reopen_task(target, response_lang)

    if action == "delete_task":
        return delete_task(target, response_lang)

    return None
