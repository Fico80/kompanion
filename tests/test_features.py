import sys
import os
import tempfile
import unittest

# Backend on path, stay offline (no embeddings / LLM), isolated throwaway DB
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))
os.environ.pop("NVIDIA_NIM_API_KEY", None)

import memory  # noqa: E402
memory._DB_PATH = os.path.join(tempfile.mkdtemp(), "test_features.db")
memory.init_db()

import main  # noqa: E402  (imports the same `memory` module object)
os.environ.pop("NVIDIA_NIM_API_KEY", None)  # _load_env may have re-added it


class TestTaskLifecycle(unittest.TestCase):
    def setUp(self):
        with memory._conn() as c:
            c.execute("DELETE FROM tasks")
            c.commit()

    def test_add_and_list(self):
        memory.add_task("Steuer hochladen")
        memory.add_task("Rechnung zahlen", due="2026-06-01")
        tasks = memory.get_open_tasks()
        self.assertEqual(len(tasks), 2)
        # Dated task sorts before the undated one
        self.assertEqual(tasks[0]["text"], "Rechnung zahlen")

    def test_complete_and_reopen(self):
        tid = memory.add_task("Müll rausbringen")
        self.assertEqual(len(memory.get_open_tasks()), 1)
        self.assertTrue(memory.complete_task(tid))
        self.assertEqual(len(memory.get_open_tasks()), 0)
        self.assertTrue(memory.reopen_task(tid))
        self.assertEqual(len(memory.get_open_tasks()), 1)

    def test_index_and_text_lookup(self):
        memory.add_task("Erste Aufgabe", due="2026-06-01")
        memory.add_task("Zweite Aufgabe")
        self.assertEqual(memory.get_open_task_by_index(1)["text"], "Erste Aufgabe")
        self.assertIsNone(memory.get_open_task_by_index(9))
        self.assertEqual(memory.find_open_task_by_text("zweite")["text"], "Zweite Aufgabe")
        self.assertIsNone(memory.find_open_task_by_text("gibtsnicht"))

    def test_delete(self):
        tid = memory.add_task("Wegwerfen")
        self.assertTrue(memory.delete_task(tid))
        self.assertEqual(len(memory.get_open_tasks()), 0)


class TestConfirmationFlow(unittest.TestCase):
    def setUp(self):
        # Reset all pending session state
        main._pending_yesno = None
        main._pending_confirmation = None
        main._pending_selection = None
        main._last_undo = None
        # Record executions instead of really running them (no KWin)
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

    def test_close_all_asks_before_executing(self):
        r = self._run("schließe alles")
        self.assertEqual(r["parsed"]["action"], "close_all_windows")
        self.assertIsNotNone(main._pending_yesno)
        self.assertEqual(self.executed, [])  # nothing executed yet

    def test_yes_executes(self):
        self._run("schließe alles")
        r = self._run("ja")
        self.assertEqual(self.executed, ["close_all_windows"])
        self.assertIsNone(main._pending_yesno)
        self.assertEqual(r["parsed"]["_stage"], "confirm")

    def test_no_cancels(self):
        self._run("schließe alles")
        r = self._run("nein")
        self.assertEqual(self.executed, [])
        self.assertIsNone(main._pending_yesno)
        self.assertEqual(r["result"]["message"], "Abgebrochen.")

    def test_unrelated_drops_confirmation(self):
        self._run("schließe alles")
        self._run("öffne Firefox")
        self.assertIsNone(main._pending_yesno)
        self.assertIn("open_app", self.executed)


class TestUndoMapping(unittest.TestCase):
    """`_build_undo` is pure — verify the inverse action for each reversible type."""

    def test_add_task_undo_is_delete(self):
        undo = main._build_undo({"action": "add_task"}, {"task_id": 7})
        self.assertEqual(undo["action"], "delete_task")
        self.assertEqual(undo["target"], 7)

    def test_complete_task_undo_is_reopen(self):
        undo = main._build_undo({"action": "complete_task"}, {"task_id": 3})
        self.assertEqual(undo["action"], "reopen_task")
        self.assertEqual(undo["target"], 3)

    def test_volume_relative_inverts(self):
        undo = main._build_undo({"action": "set_volume", "target": "+10%"}, {})
        self.assertEqual(undo["action"], "set_volume")
        self.assertEqual(undo["target"], "-10%")

    def test_close_all_has_no_undo(self):
        self.assertIsNone(main._build_undo({"action": "close_all_windows"}, {"success": True}))


if __name__ == "__main__":
    unittest.main()
