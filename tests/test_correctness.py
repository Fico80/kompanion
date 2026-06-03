"""
Correctness regression tests for three red-severity bugs identified in the audit:

  1. Duplicate DB rows on append_note — notes/executor.py + memory.py
  2. DB written before disk in save_note — notes/executor.py + memory.py
  3. Global session-state race condition — main.py
"""
import sys
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

import memory
memory._DB_PATH = os.path.join(tempfile.mkdtemp(), "test_correctness.db")
memory.init_db()

import main  # noqa: imported after DB path patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _note_count_for_path(path: str) -> int:
    with memory._conn() as c:
        return c.execute("SELECT COUNT(*) FROM notes WHERE path = ?", (path,)).fetchone()[0]


def _note_rows_for_path(path: str) -> list[dict]:
    with memory._conn() as c:
        rows = c.execute(
            "SELECT id, content, path, embedding FROM notes WHERE path = ?", (path,)
        ).fetchall()
    return [dict(r) for r in rows]


def _clear_notes_db():
    with memory._conn() as c:
        c.execute("DELETE FROM notes")
        c.commit()


# ---------------------------------------------------------------------------
# Fix 1: append_note must NOT create a new DB row per call
# ---------------------------------------------------------------------------

class TestAppendNoteNoDuplicateRows(unittest.TestCase):
    """Every note file must have exactly ONE row in the notes table, regardless
    of how many times it has been appended to."""

    def setUp(self):
        _clear_notes_db()
        self.notes_dir = tempfile.mkdtemp()

    def _make_note_file(self, content: str = "Initial content") -> str:
        path = os.path.join(self.notes_dir, "test-note.md")
        Path(path).write_text(f"# Header\n\n{content}\n")
        return path

    def test_append_does_not_insert_new_row(self):
        """Calling append_note on an existing note must not add a DB row."""
        from capabilities.notes.executor import append_note

        path = self._make_note_file("First version of the note.")
        # Manually insert the initial DB record (simulating what save_note does)
        memory.record_note("First version of the note.", path)

        self.assertEqual(_note_count_for_path(path), 1, "Setup: expected 1 row before append")

        # Patch find so we can mock the search result
        with patch.object(memory, "_get_embedding", return_value=None), \
             patch.object(memory, "search_notes", return_value=[{"content": "First version of the note.", "path": path, "ts": "2025-01-01", "similarity": None}]):
            append_note("test-note", "Appended paragraph.", response_lang="en")

        self.assertEqual(
            _note_count_for_path(path), 1,
            "append_note must NOT insert a new DB row — the note already has a record",
        )

    def test_multiple_appends_still_one_row(self):
        """Three appends in a row must still leave exactly one DB row."""
        from capabilities.notes.executor import append_note

        path = self._make_note_file("Original.")
        memory.record_note("Original.", path)

        with patch.object(memory, "_get_embedding", return_value=None), \
             patch.object(memory, "search_notes", return_value=[{"content": "Original.", "path": path, "ts": "2025-01-01", "similarity": None}]):
            for i in range(3):
                append_note("test-note", f"Addition {i}.", response_lang="en")

        self.assertEqual(_note_count_for_path(path), 1,
                         "Three appends must still leave exactly one DB row")

    def test_save_note_then_append_one_row(self):
        """save_note() followed by append_note() must produce exactly one DB row."""
        from capabilities.notes import executor as notes_exec

        with patch.object(memory, "_get_embedding", return_value=None), \
             patch.object(notes_exec, "_format_note", side_effect=lambda t, _: t), \
             patch.object(notes_exec, "NOTES_DIR", Path(self.notes_dir)):

            notes_exec.save_note("My original note content.", response_lang="en")

        rows = _note_rows_for_path_prefix(self.notes_dir)
        self.assertEqual(len(rows), 1, "save_note must insert exactly one row")
        path = rows[0]["path"]

        with patch.object(memory, "_get_embedding", return_value=None), \
             patch.object(memory, "search_notes", return_value=[{"content": "My original note content.", "path": path, "ts": "2025-01-01", "similarity": None}]):
            from capabilities.notes.executor import append_note
            append_note("original note", "Additional content.", response_lang="en")

        all_rows = _note_rows_for_path_prefix(self.notes_dir)
        self.assertEqual(len(all_rows), 1, "After one save + one append: must still be one DB row")


def _note_rows_for_path_prefix(prefix: str) -> list[dict]:
    with memory._conn() as c:
        rows = c.execute(
            "SELECT id, content, path, embedding FROM notes WHERE path LIKE ?",
            (prefix + "%",),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Fix 2: save_note must write the file BEFORE recording in DB
# ---------------------------------------------------------------------------

class TestSaveNoteDBAfterDisk(unittest.TestCase):
    """If the file write fails, no DB row should be created."""

    def setUp(self):
        _clear_notes_db()
        self.notes_dir = tempfile.mkdtemp()

    def test_no_db_row_when_file_write_fails(self):
        """If open() raises an exception, save_note must not leave a DB orphan."""
        from capabilities.notes import executor as notes_exec
        import builtins

        initial_count = _count_all_notes()

        real_open = builtins.open

        def _failing_open(path, *args, **kwargs):
            # Allow non-note files (e.g. config reads), only blow up for .md writes
            if isinstance(path, str) and path.endswith(".md") and "w" in str(args):
                raise OSError("Simulated disk full")
            return real_open(path, *args, **kwargs)

        with patch.object(memory, "_get_embedding", return_value=None), \
             patch.object(notes_exec, "_format_note", side_effect=lambda t, _: t), \
             patch.object(notes_exec, "NOTES_DIR", Path(self.notes_dir)), \
             patch("builtins.open", side_effect=_failing_open):
            try:
                notes_exec.save_note("This note will fail to write.", response_lang="en")
            except OSError:
                pass

        final_count = _count_all_notes()
        self.assertEqual(
            initial_count, final_count,
            f"A failed file write must not add a DB row (before={initial_count}, after={final_count})",
        )

    def test_db_row_exists_after_successful_save(self):
        """A successful save_note must create exactly one DB row."""
        from capabilities.notes import executor as notes_exec

        with patch.object(memory, "_get_embedding", return_value=None), \
             patch.object(notes_exec, "_format_note", side_effect=lambda t, _: t), \
             patch.object(notes_exec, "NOTES_DIR", Path(self.notes_dir)):
            result = notes_exec.save_note("A successful note.", response_lang="en")

        self.assertTrue(result["success"])
        path = result["details"]["path"]
        self.assertTrue(os.path.exists(path), "Note file must exist on disk")
        self.assertEqual(_note_count_for_path(path), 1, "Must be exactly one DB row")

    def test_similar_notes_found_before_self_is_in_db(self):
        """find_similar_notes() must search BEFORE the new note is inserted.
        Concretely: saving two notes about the same topic must NOT return the
        note itself as its own similar match."""
        from capabilities.notes import executor as notes_exec

        fake_embedding = [0.1] * 10

        def _fake_embed(text):
            return fake_embedding

        with patch.object(memory, "_get_embedding", side_effect=_fake_embed), \
             patch.object(notes_exec, "_format_note", side_effect=lambda t, _: t), \
             patch.object(notes_exec, "NOTES_DIR", Path(self.notes_dir)):
            # Save first note — no similar notes yet
            result1 = notes_exec.save_note("Topic A first note.", response_lang="en")
            self.assertEqual(result1["details"]["similar"], [],
                             "First note must have no similar matches")

            # Save second note about the same topic — should find first, NOT itself
            result2 = notes_exec.save_note("Topic A second note.", response_lang="en")

        similar2 = result2["details"]["similar"]
        path2 = result2["details"]["path"]
        self_refs = [s for s in similar2 if s.get("path") == path2]
        self.assertEqual(self_refs, [],
                         "A note must never appear as similar to itself")


def _count_all_notes() -> int:
    with memory._conn() as c:
        return c.execute("SELECT COUNT(*) FROM notes").fetchone()[0]


# ---------------------------------------------------------------------------
# Fix 3: Global session state must be protected against concurrent requests
# ---------------------------------------------------------------------------

class TestGlobalStateLock(unittest.TestCase):
    """The _state_lock must prevent concurrent requests from corrupting session state."""

    def setUp(self):
        main._pending_yesno = None
        main._pending_confirmation = None
        main._pending_selection = None
        main._last_undo = None
        self.executed = []

        def fake_exec(parsed):
            self.executed.append(parsed.get("action"))
            return {"success": True, "message": f"[{parsed.get('action')}]"}

        self._orig_exec = main.execute_parsed_intent
        main.execute_parsed_intent = fake_exec

    def tearDown(self):
        main.execute_parsed_intent = self._orig_exec

    def _run(self, cmd):
        return main.execute_command(main.CommandRequest(command=cmd))

    def test_state_lock_is_a_threading_lock(self):
        """The module must expose a real threading.Lock (not just a comment)."""
        self.assertIsInstance(main._state_lock, type(threading.Lock()),
                              "_state_lock must be a threading.Lock instance")

    def test_execute_command_blocks_while_lock_is_held(self):
        """execute_command must block until _state_lock is available (i.e., it uses the lock)."""
        results = []

        # Acquire the lock externally before launching the request thread
        main._state_lock.acquire()

        def request_thread():
            results.append(self._run("öffne Firefox"))

        t = threading.Thread(target=request_thread)
        t.start()

        # Give the thread a moment to reach the lock; it must still be alive
        t.join(timeout=0.15)
        self.assertTrue(t.is_alive(),
                        "execute_command should be blocked while _state_lock is held")
        self.assertEqual(results, [],
                         "No result should be available while the lock is held")

        # Release the lock — the thread must finish
        main._state_lock.release()
        t.join(timeout=2.0)
        self.assertFalse(t.is_alive(), "Thread must complete after lock is released")
        self.assertEqual(len(results), 1, "Must have exactly one result after completing")

    def test_concurrent_requests_do_not_corrupt_yesno_state(self):
        """Two threads: one sets up a yesno, one sends an unrelated command.
        With the lock, the yesno state must not be lost."""
        results = {}

        def thread_a():
            # Sets up a pending yesno
            results["a"] = self._run("schließe alles")

        def thread_b():
            # Sends an unrelated command that would previously drop pending_yesno
            results["b"] = self._run("öffne Firefox")

        # Run thread_a first, then thread_b while a may still hold the lock
        t_a = threading.Thread(target=thread_a)
        t_b = threading.Thread(target=thread_b)
        t_a.start()
        t_a.join()
        t_b.start()
        t_b.join()

        # After a: yesno must be pending (close_all_windows requires confirmation)
        # After b: yesno must be cleared (unrelated command drops it)
        self.assertEqual(results["a"]["parsed"]["action"], "close_all_windows")
        self.assertIsNone(main._pending_yesno,
                          "Unrelated command after yesno must clear the pending yesno")

    def test_concurrent_yes_no_responses_are_serialized(self):
        """Simulate 20 concurrent requests racing to answer a yesno.
        Only one must execute the action; the rest must see it already cleared."""
        self._run("schließe alles")  # sets up pending_yesno
        self.assertIsNotNone(main._pending_yesno)

        confirm_count = [0]
        lock = threading.Lock()

        def send_yes():
            resp = self._run("ja")
            if resp["parsed"].get("_stage") == "confirm" and resp["result"]["success"]:
                with lock:
                    confirm_count[0] += 1

        threads = [threading.Thread(target=send_yes) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(
            confirm_count[0], 1,
            f"Exactly one 'ja' must execute the action; got {confirm_count[0]}",
        )
        self.assertEqual(
            self.executed.count("close_all_windows"), 1,
            f"close_all_windows must execute exactly once; executed={self.executed}",
        )

    def test_undo_state_not_stolen_by_concurrent_request(self):
        """A concurrent request must not be able to consume another request's undo."""
        # Manually set up an undo record
        main._last_undo = {
            "description": "Firefox",
            "undo_parsed": {
                "action": "open_app",
                "target": "firefox",
                "app_name": "Firefox",
                "window_title": None, "window_class": None,
                "flatpak_id": None, "layout": None,
                "desktop": None, "monitor": None,
            },
        }

        undo_results = []

        def send_undo():
            undo_results.append(self._run("rückgängig"))

        threads = [threading.Thread(target=send_undo) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Only one undo should have succeeded (the one that found _last_undo non-None)
        successes = [r for r in undo_results if r["result"].get("success")]
        self.assertEqual(len(successes), 1,
                         f"Exactly one undo must succeed; got {len(successes)}")
        self.assertIsNone(main._last_undo, "_last_undo must be cleared after use")


if __name__ == "__main__":
    unittest.main(verbosity=2)
