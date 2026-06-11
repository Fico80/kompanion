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
from capabilities.audio import executor as audio_executor  # noqa: E402
from capabilities.brightness import executor as brightness_executor  # noqa: E402
from capabilities.timer import executor as timer_executor  # noqa: E402
from capabilities.weather import executor as weather_executor  # noqa: E402
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

    def test_due_tasks_skip_done_future_and_already_notified(self):
        overdue = memory.add_task("Überfällig", due="2026-06-01")
        today = memory.add_task("Heute", due="2026-06-11")
        future = memory.add_task("Zukunft", due="2026-06-12")
        done = memory.add_task("Erledigt", due="2026-06-01")
        memory.add_task("Ohne Datum")
        memory.complete_task(done)

        due = memory.get_due_tasks("2026-06-11")
        self.assertEqual({t["id"] for t in due}, {overdue, today})

        memory.mark_task_notified(overdue, "2026-06-11")
        due_after_notify = memory.get_due_tasks("2026-06-11")
        self.assertEqual({t["id"] for t in due_after_notify}, {today})

        due_next_day = memory.get_due_tasks("2026-06-12")
        self.assertEqual({t["id"] for t in due_next_day}, {overdue, today, future})


class TestTimerExecution(unittest.TestCase):
    def test_set_timer_starts_daemon_timer_without_firing_immediately(self):
        created = []

        class FakeTimer:
            def __init__(self, duration, callback):
                self.duration = duration
                self.callback = callback
                self.daemon = False
                self.started = False
                created.append(self)

            def start(self):
                self.started = True

        original_timer = timer_executor.threading.Timer
        try:
            timer_executor.threading.Timer = FakeTimer
            result = timer_executor.set_timer(7200, "Hausübung", "de")
        finally:
            timer_executor.threading.Timer = original_timer

        self.assertTrue(result["success"])
        self.assertEqual(result["message"], "Timer: 2 Stunden — Hausübung")
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].duration, 7200)
        self.assertTrue(created[0].daemon)
        self.assertTrue(created[0].started)


class TestWeatherExecution(unittest.TestCase):
    def test_day_after_tomorrow_uses_third_forecast_day(self):
        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                def day(avg, desc):
                    return {
                        "mintempC": str(int(avg) - 2),
                        "maxtempC": str(int(avg) + 2),
                        "avgtempC": str(avg),
                        "hourly": [{"weatherDesc": [{"value": desc}]}],
                    }

                return {
                    "current_condition": [{
                        "temp_C": "10",
                        "FeelsLikeC": "9",
                        "humidity": "70",
                        "windspeedKmph": "12",
                        "weatherDesc": [{"value": "Cloudy"}],
                    }],
                    "weather": [
                        day(10, "Cloudy"),
                        day(11, "Light rain"),
                        day(22, "Sunny"),
                    ],
                    "nearest_area": [{"areaName": [{"value": "Wien"}]}],
                }

        original_get = weather_executor.requests.get
        try:
            weather_executor.requests.get = lambda *args, **kwargs: FakeResponse()
            result = weather_executor.query_weather("Wien", response_lang="de", day="day_after_tomorrow")
        finally:
            weather_executor.requests.get = original_get

        self.assertTrue(result["success"])
        self.assertIn("übermorgen", result["message"])
        self.assertIn("22°C", result["message"])
        self.assertIn("Sonnig", result["message"])


class TestAudioExecution(unittest.TestCase):
    def test_absolute_volume_sets_pactl_and_records_previous_volume(self):
        calls = []
        original_run = audio_executor.subprocess.run
        original_get_current = audio_executor.get_current_volume
        try:
            audio_executor.get_current_volume = lambda: "25%"

            def fake_run(cmd, **kwargs):
                calls.append(cmd)

                class Result:
                    returncode = 0
                    stdout = ""
                    stderr = ""

                return Result()

            audio_executor.subprocess.run = fake_run
            result = audio_executor.execute({
                "action": "set_volume",
                "target": "50%",
                "app_name": "Lautstärke 50%",
                "lang": "de",
            })
        finally:
            audio_executor.subprocess.run = original_run
            audio_executor.get_current_volume = original_get_current

        self.assertTrue(result["success"])
        self.assertEqual(result["prev_volume"], "25%")
        self.assertEqual(calls, [["pactl", "set-sink-volume", "@DEFAULT_SINK@", "50%"]])


class TestBrightnessExecution(unittest.TestCase):
    def test_relative_brightness_reads_current_clamps_and_sets_value(self):
        calls = []
        original_which = brightness_executor.shutil.which
        original_run = brightness_executor.subprocess.run
        original_left_display = os.environ.get("DDCUTIL_LEFT_DISPLAY")
        try:
            os.environ["DDCUTIL_LEFT_DISPLAY"] = "1"
            brightness_executor.shutil.which = lambda name: "/usr/bin/ddcutil"

            def fake_run(cmd, **kwargs):
                calls.append(cmd)

                class Result:
                    returncode = 0
                    stdout = "VCP code 0x10 (Brightness): current value = 95, max value = 100"
                    stderr = ""

                return Result()

            brightness_executor.subprocess.run = fake_run
            result = brightness_executor.set_brightness("+10%", 0, "de")
        finally:
            brightness_executor.shutil.which = original_which
            brightness_executor.subprocess.run = original_run
            if original_left_display is None:
                os.environ.pop("DDCUTIL_LEFT_DISPLAY", None)
            else:
                os.environ["DDCUTIL_LEFT_DISPLAY"] = original_left_display

        self.assertTrue(result["success"])
        self.assertEqual(calls[0], ["ddcutil", "--display", "1", "getvcp", "10"])
        self.assertEqual(calls[1], ["ddcutil", "--display", "1", "setvcp", "10", "100"])
        self.assertIn("100%", result["message"])


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
