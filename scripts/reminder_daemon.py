#!/usr/bin/env python3
"""
Reminder daemon. Checks due tasks every 15 minutes and sends desktop notifications.

Each task is notified at most once per day through notified_date in the database.
Overdue tasks are reported as well until they are completed.
"""
import sys
import os
import time
import subprocess
from datetime import date

# Ensure backend is importable regardless of cwd
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../backend")
sys.path.insert(0, backend_dir)

def _load_env():
    env_path = os.path.join(backend_dir, "../.env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

_load_env()

import memory

CHECK_INTERVAL = 15 * 60  # seconds


def _notify(title: str, body: str):
    subprocess.run(
        ["notify-send", "-u", "normal", "-t", "0", "-i", "appointment", title, body],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def check_and_notify():
    today = date.today().isoformat()
    due_tasks = memory.get_due_tasks(today)
    if not due_tasks:
        return

    for task in due_tasks:
        task_date = task.get("due", "")
        if task_date < today:
            title = "⚠️ Overdue task"
        else:
            title = "🔔 Reminder"

        _notify(title, task["text"])
        memory.mark_task_notified(task["id"], today)
        print(f"[REMINDER] {title}: {task['text']}")

    # If multiple tasks due: send a summary notification too
    if len(due_tasks) > 1:
        count = len(due_tasks)
        _notify(
            f"📋 {count} tasks due today",
            "\n".join(f"• {t['text']}" for t in due_tasks),
        )


def main():
    memory.init_db()
    print(f"[REMINDER] Daemon started. Checking every {CHECK_INTERVAL // 60} minutes.")

    # Check immediately on startup
    check_and_notify()

    while True:
        time.sleep(CHECK_INTERVAL)
        try:
            check_and_notify()
        except Exception as e:
            print(f"[REMINDER] Error: {e}")


if __name__ == "__main__":
    main()
