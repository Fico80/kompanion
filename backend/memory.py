import sqlite3
import os
import json
import requests
import numpy as np
from contextlib import contextmanager
from datetime import datetime, timedelta
from shared.paths import MEMORY_DB

_DB_PATH = str(MEMORY_DB)
_SIMILARITY_THRESHOLD = 0.75

_embed_base = os.environ.get("EMBED_BASE_URL", "").rstrip("/")
_EMBED_URL   = (_embed_base + "/embeddings") if _embed_base and not _embed_base.endswith("/embeddings") else _embed_base
_EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")

@contextmanager
def _conn():
    """Open a SQLite connection, yield it, and always close it on exit."""
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        TEXT    NOT NULL,
                raw_text  TEXT,
                action    TEXT,
                target    TEXT,
                app_name  TEXT,
                stage     TEXT,
                success   INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        TEXT    NOT NULL,
                content   TEXT    NOT NULL,
                path      TEXT,
                embedding TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                ts            TEXT    NOT NULL,
                text          TEXT    NOT NULL,
                due           TEXT,
                done          INTEGER DEFAULT 0,
                done_ts       TEXT,
                notified_date TEXT
            )
        """)
        # Migration: add notified_date to existing tables that were created without it
        try:
            conn.execute("ALTER TABLE tasks ADD COLUMN notified_date TEXT")
            conn.commit()
        except Exception:
            pass  # column already exists
        conn.commit()
    # Ensure the DB file is owner-only regardless of the process umask.
    try:
        import stat
        if stat.S_IMODE(os.stat(_DB_PATH).st_mode) & 0o077:
            os.chmod(_DB_PATH, 0o600)
    except OSError:
        pass

# --- Tasks ---

# Open tasks are ordered with dated ones first (soonest due first), undated last,
# then by creation time. The display order and 1-based index used by "erledige Aufgabe N"
# must stay identical, so both queries share this ORDER BY clause.
_TASK_ORDER = "ORDER BY (due IS NULL), due ASC, ts ASC"

def add_task(text: str, due: str | None = None) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (ts, text, due, done) VALUES (?,?,?,0)",
            (datetime.now().isoformat(timespec="seconds"), text, due),
        )
        conn.commit()
        return cur.lastrowid

def get_open_tasks() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT id, ts, text, due FROM tasks WHERE done = 0 {_TASK_ORDER}"
        ).fetchall()
    return [dict(r) for r in rows]

def get_open_task_by_index(index: int) -> dict | None:
    """1-based index into the open-task list (same order as get_open_tasks)."""
    tasks = get_open_tasks()
    if 1 <= index <= len(tasks):
        return tasks[index - 1]
    return None

def find_open_task_by_text(ref: str) -> dict | None:
    """Find an open task whose text contains `ref` (case-insensitive). Prefers the shortest match."""
    ref = (ref or "").strip().lower()
    if not ref:
        return None
    matches = [t for t in get_open_tasks() if ref in t["text"].lower()]
    if not matches:
        return None
    return min(matches, key=lambda t: len(t["text"]))

def complete_task(task_id: int) -> bool:
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE tasks SET done = 1, done_ts = ? WHERE id = ? AND done = 0",
            (datetime.now().isoformat(timespec="seconds"), task_id),
        )
        conn.commit()
        return cur.rowcount > 0

def reopen_task(task_id: int) -> bool:
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE tasks SET done = 0, done_ts = NULL WHERE id = ?", (task_id,)
        )
        conn.commit()
        return cur.rowcount > 0

def delete_task(task_id: int) -> bool:
    with _conn() as conn:
        cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        return cur.rowcount > 0

def get_due_tasks(today: str) -> list[dict]:
    """Tasks that are due today or overdue, not done, and not yet notified today."""
    with _conn() as conn:
        rows = conn.execute(
            """SELECT id, text, due FROM tasks
               WHERE done = 0
               AND due IS NOT NULL
               AND due <= ?
               AND (notified_date IS NULL OR notified_date < ?)""",
            (today, today),
        ).fetchall()
    return [dict(r) for r in rows]

def mark_task_notified(task_id: int, date: str):
    """Record that a notification was sent for this task on `date`."""
    with _conn() as conn:
        conn.execute("UPDATE tasks SET notified_date = ? WHERE id = ?", (date, task_id))
        conn.commit()

# --- Command history ---

def log_command(raw_text: str, parsed: dict, success: bool):
    with _conn() as conn:
        conn.execute(
            "INSERT INTO history (ts, raw_text, action, target, app_name, stage, success) VALUES (?,?,?,?,?,?,?)",
            (
                datetime.now().isoformat(timespec="seconds"),
                raw_text,
                parsed.get("action"),
                parsed.get("target"),
                parsed.get("app_name"),
                parsed.get("_stage"),
                1 if success else 0,
            ),
        )
        conn.commit()

def get_recent(limit: int = 10) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT ts, raw_text, action, app_name, success FROM history ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]

def get_top_commands(limit: int = 10) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT app_name, action, target, COUNT(*) as count
               FROM history WHERE success = 1
               GROUP BY action, target
               ORDER BY count DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]

def get_stats() -> dict:
    with _conn() as conn:
        total   = conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        success = conn.execute("SELECT COUNT(*) FROM history WHERE success=1").fetchone()[0]
        today   = conn.execute(
            "SELECT COUNT(*) FROM history WHERE ts >= ?",
            (datetime.now().date().isoformat(),),
        ).fetchone()[0]
    return {"total": total, "success": success, "today": today}

# --- Embeddings ---

def _get_embedding(text: str) -> list[float] | None:
    if not _EMBED_URL:
        return None
    key = os.environ.get("EMBED_API_KEY", os.environ.get("LLM_API_KEY", ""))
    using_local = any(h in _EMBED_URL for h in ("localhost", "127.0.0.1", "::1", "0.0.0.0"))
    if not key and not using_local:
        return None
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        resp = requests.post(
            _EMBED_URL,
            headers=headers,
            json={"input": [text], "model": _EMBED_MODEL},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]
    except Exception:
        return None

def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denom) if denom else 0.0

def _find_similar(query_emb: list[float], exclude_content: str, top_k: int = 3) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT content, path, ts, embedding FROM notes WHERE embedding IS NOT NULL"
        ).fetchall()

    scored = []
    for row in rows:
        if row["content"] == exclude_content:
            continue
        sim = _cosine(query_emb, json.loads(row["embedding"]))
        if sim >= _SIMILARITY_THRESHOLD:
            scored.append({"content": row["content"], "path": row["path"], "ts": row["ts"][:10], "similarity": round(sim, 3)})

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:top_k]

# --- Notes ---

def _insert_note(content: str, path: str, embedding: list[float] | None) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO notes (ts, content, path, embedding) VALUES (?,?,?,?)",
            (
                datetime.now().isoformat(timespec="seconds"),
                content,
                path,
                json.dumps(embedding) if embedding else None,
            ),
        )
        conn.commit()


def find_similar_notes(content: str, top_k: int = 3) -> list[dict]:
    """Return notes similar to content WITHOUT inserting anything. Returns [] when embeddings are unavailable."""
    embedding = _get_embedding(content)
    if not embedding:
        return []
    return _find_similar(embedding, content, top_k)


def record_note(content: str, path: str) -> None:
    """Insert a note record into the DB including its embedding."""
    embedding = _get_embedding(content)
    _insert_note(content, path, embedding)


def update_note_embedding(path: str, new_content: str) -> None:
    """Re-embed and update the existing DB record(s) for path (used when a note is appended to)."""
    embedding = _get_embedding(new_content)
    if not embedding:
        return
    with _conn() as conn:
        conn.execute(
            "UPDATE notes SET embedding = ? WHERE path = ?",
            (json.dumps(embedding), path),
        )
        conn.commit()


def save_note(content: str, path: str) -> list[dict]:
    """Embed + store note, return list of similar existing notes.

    Kept for backward compatibility. Prefer find_similar_notes() + record_note()
    when you need to write the file between the two steps.
    """
    embedding = _get_embedding(content)
    similar = _find_similar(embedding, content) if embedding else []
    _insert_note(content, path, embedding)
    return similar

def detect_sequences(window_minutes: int = 10, min_count: int = 3, days: int = 30) -> list[dict]:
    """Find repeated multi-step app/url launch patterns in the command history."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    with _conn() as conn:
        rows = conn.execute(
            """SELECT ts, raw_text, action, app_name, target
               FROM history
               WHERE success = 1 AND ts > ? AND action IN ('open_app', 'open_url')
               AND raw_text IS NOT NULL
               ORDER BY ts ASC""",
            (cutoff,),
        ).fetchall()

    rows = [dict(r) for r in rows]
    if len(rows) < 2:
        return []

    # Split into sessions: gap > window_minutes = new session
    sessions: list = []
    current: list = [rows[0]]
    for r in rows[1:]:
        delta = (datetime.fromisoformat(r["ts"]) - datetime.fromisoformat(current[-1]["ts"])).total_seconds()
        if delta > window_minutes * 60:
            if len(current) >= 2:
                sessions.append(current)
            current = [r]
        else:
            current.append(r)
    if len(current) >= 2:
        sessions.append(current)

    from collections import Counter
    counter: Counter = Counter()
    examples: dict = {}

    for session in sessions:
        n = len(session)
        for length in range(2, min(n + 1, 6)):
            for i in range(n - length + 1):
                sub = session[i : i + length]
                key = tuple(
                    (s["action"], (s["app_name"] or s["target"] or "").lower())
                    for s in sub
                )
                counter[key] += 1
                examples[key] = [s["raw_text"] for s in sub]  # keep most recent occurrence

    results = []
    for key, count in counter.most_common(5):
        if count < min_count:
            break
        results.append({
            "count": count,
            "commands": examples[key],
            "apps": [k[1] for k in key if k[1]],
        })
    return results

def get_top_sequence() -> dict | None:
    seqs = detect_sequences()
    return seqs[0] if seqs else None

def get_suggestions(min_count: int = 4, days: int = 30) -> list[dict]:
    """Return most frequently used successful commands of the last N days."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    with _conn() as conn:
        rows = conn.execute(
            """SELECT raw_text AS command, action, app_name, target, COUNT(*) AS count
               FROM history
               WHERE success = 1 AND ts > ?
               GROUP BY LOWER(raw_text)
               HAVING count >= ?
               ORDER BY count DESC
               LIMIT 8""",
            (cutoff, min_count),
        ).fetchall()
    return [dict(r) for r in rows]

def _filter_existing(rows) -> list[dict]:
    return [dict(r) for r in rows if not r["path"] or os.path.exists(r["path"])]

def get_notes(limit: int = 20) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT ts, content, path FROM notes ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
    return _filter_existing(rows)

def get_notes_since(days: int, limit: int = 50) -> list[dict]:
    """Notes created within the last `days` days, newest first."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT ts, content, path FROM notes WHERE ts > ? ORDER BY ts DESC LIMIT ?",
            (cutoff, limit),
        ).fetchall()
    return _filter_existing(rows)

def search_notes(query: str, top_k: int = 5, threshold: float = 0.4) -> list[dict]:
    """Semantic search over stored notes. Falls back to substring match if embeddings are unavailable."""
    query_emb = _get_embedding(query)
    with _conn() as conn:
        rows = conn.execute("SELECT content, path, ts, embedding FROM notes").fetchall()

    if query_emb:
        scored = []
        for r in rows:
            if not r["embedding"]:
                continue
            if r["path"] and not os.path.exists(r["path"]):
                continue
            sim = _cosine(query_emb, json.loads(r["embedding"]))
            if sim >= threshold:
                scored.append({"content": r["content"], "path": r["path"],
                               "ts": r["ts"], "similarity": round(sim, 3)})
        scored.sort(key=lambda x: x["similarity"], reverse=True)
        if scored:
            return scored[:top_k]
        # Embeddings available but nothing crossed the threshold → fall through to substring match

    # Fallback: case-insensitive substring match on the note content
    q = query.lower().strip()
    subs = [
        {"content": r["content"], "path": r["path"], "ts": r["ts"], "similarity": None}
        for r in rows
        if q and q in r["content"].lower()
        and (not r["path"] or os.path.exists(r["path"]))
    ]
    return subs[:top_k]
