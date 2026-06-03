import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

import unittest
from parser import _parse_regex as parse_regex, parse_command


def parse_basic_command(text):
    return parse_regex(text)

class TestParser(unittest.TestCase):
    def test_open_apps(self):
        res = parse_basic_command("Öffne VS Code")
        self.assertEqual(res["action"], "open_app")
        self.assertEqual(res["target"], "code")
        self.assertEqual(res["app_name"], "VS Code")
        
        res = parse_basic_command("öffne firefox")
        self.assertEqual(res["action"], "open_app")
        self.assertEqual(res["target"], "firefox")
        
        res = parse_basic_command("starte zapzap")
        self.assertEqual(res["action"], "open_app")
        self.assertEqual(res["target"], "zapzap")

        res = parse_basic_command("open console")
        self.assertEqual(res["action"], "open_app")
        self.assertEqual(res["target"], "konsole")

    def test_open_urls(self):
        res = parse_basic_command("Öffne Perplexity")
        self.assertEqual(res["action"], "open_url")
        self.assertEqual(res["target"], "https://www.perplexity.ai")
        self.assertEqual(res["window_title"], "Perplexity")
        
        res = parse_basic_command("Öffne google")
        self.assertEqual(res["action"], "open_url")
        self.assertEqual(res["target"], "https://www.google.com")

    def test_layouts(self):
        res = parse_basic_command("Öffne Firefox links")
        self.assertEqual(res["layout"], "left")
        self.assertEqual(res["target"], "firefox")
        
        res = parse_basic_command("Öffne google rechts")
        self.assertEqual(res["layout"], "right")
        self.assertEqual(res["action"], "open_url")

    def test_desktops(self):
        res = parse_basic_command("Öffne Spotify auf Arbeitsfläche 2")
        self.assertEqual(res["desktop"], 1)
        self.assertEqual(res["target"], "spotify")
        
        res = parse_basic_command("Öffne VS Code auf Workspace 3 links")
        self.assertEqual(res["desktop"], 2)
        self.assertEqual(res["layout"], "left")

    def test_monitors(self):
        res = parse_basic_command("Öffne Firefox auf linkem Monitor")
        self.assertEqual(res["monitor"], 0)
        
        res = parse_basic_command("Öffne Spotify auf rechtem Bildschirm rechts")
        self.assertEqual(res["monitor"], 1)
        self.assertEqual(res["layout"], "right")

    def test_folders(self):
        res = parse_basic_command("Öffne Ordner Downloads")
        self.assertEqual(res["action"], "open_path")
        self.assertTrue(res["target"].endswith("Downloads"))
        
        res = parse_basic_command("Öffne /home/fico/Documents")
        self.assertEqual(res["action"], "open_path")
        self.assertEqual(res["target"], "/home/fico/Documents")

    def test_brightness(self):
        res = parse_command("Setze die Bildschirmhelligkeit auf 80 Prozent")
        self.assertEqual(res["action"], "set_brightness")
        self.assertEqual(res["target"], "80%")
        self.assertIsNone(res["monitor"])

        res = parse_command("Mach den linken Monitor heller um 20 Prozent")
        self.assertEqual(res["action"], "set_brightness")
        self.assertEqual(res["target"], "+20%")
        self.assertEqual(res["monitor"], 0)

        res = parse_command("rechter Bildschirm dunkler")
        self.assertEqual(res["action"], "set_brightness")
        self.assertEqual(res["target"], "-10%")
        self.assertEqual(res["monitor"], 1)


class TestPipelineStages(unittest.TestCase):
    """Routing coverage: each command must land in the intended stage."""

    def assertStage(self, command, action, stage=None):
        res = parse_command(command)
        self.assertEqual(res.get("action"), action, f"{command!r} → {res.get('action')} (stage {res.get('_stage')})")
        if stage:
            self.assertEqual(res.get("_stage"), stage, f"{command!r} landed in stage {res.get('_stage')}")
        return res

    def test_spotify_before_audio(self):
        self.assertStage("spiele den Song Bohemian Rhapsody", "control_spotify", "spotify")

    def test_app_volume_vs_global(self):
        self.assertStage("Spotify leiser", "set_app_volume", "app_volume")
        self.assertStage("Lautstärke auf 30", "set_volume", "audio")

    def test_timer_with_duration(self):
        self.assertStage("erinnere mich in 10 Minuten ans Meeting", "set_timer", "timer")

    def test_calendar_not_stolen_by_task(self):
        self.assertStage("was steht heute im Kalender", "query_calendar", "kalender")
        self.assertStage("erstelle Termin Zahnarzt morgen um 9 Uhr", "create_calendar_event", "kalender_neu")

    def test_note_creation(self):
        self.assertStage("notiere dass ich Brot kaufen muss", "save_note", "notiz")

    def test_clipboard_not_stolen_by_knowledge(self):
        self.assertStage("fasse das zusammen", "clipboard_task", "clipboard")
        self.assertStage("fasse den Text zusammen", "clipboard_task", "clipboard")

    def test_file_search_not_stolen_by_knowledge(self):
        self.assertStage("suche das PDF in Downloads", "search_files", "suche")
        self.assertStage("finde meine Urlaubsfotos", "search_files", "suche")

    def test_weather_language_and_day(self):
        res = self.assertStage("how is the weather tomorrow", "query_weather", "wetter")
        self.assertEqual(res.get("lang"), "en")
        self.assertEqual(res.get("weather_day"), "tomorrow")

        res = self.assertStage("wie ist das wetter morgen", "query_weather", "wetter")
        self.assertEqual(res.get("lang"), "de")
        self.assertEqual(res.get("weather_day"), "tomorrow")


class TestCloseAndConfirm(unittest.TestCase):
    def test_close_single_app(self):
        res = parse_command("schließe Firefox")
        self.assertEqual(res["action"], "close_app")
        self.assertEqual(res["window_class"], "firefox")
        self.assertFalse(res.get("requires_confirmation", False))

    def test_close_all_requires_confirmation(self):
        for cmd in ["schließe alles", "beende alle Fenster", "mach alle apps zu"]:
            res = parse_command(cmd)
            self.assertEqual(res["action"], "close_all_windows", cmd)
            self.assertTrue(res.get("requires_confirmation"), cmd)
            self.assertTrue(res.get("confirm_prompt"), cmd)

    def test_move_active_window(self):
        res = parse_command("verschiebe aktives Fenster rechts")
        self.assertEqual(res["action"], "move_window")
        self.assertEqual(res["target"], "__active_window__")
        self.assertEqual(res["layout"], "right")

        res = parse_command("mache es rechts")
        self.assertEqual(res["action"], "move_window")
        self.assertEqual(res["target"], "__active_window__")
        self.assertEqual(res["layout"], "right")

        res = parse_command("schiebe es nach rechts")
        self.assertEqual(res["action"], "move_window")
        self.assertEqual(res["target"], "__active_window__")
        self.assertEqual(res["layout"], "right")

        res = parse_command("schiebe es auf den rechten Monitor")
        self.assertEqual(res["action"], "move_window")
        self.assertEqual(res["target"], "__active_window__")
        self.assertEqual(res["monitor"], 1)

        res = parse_command("schiebe es auf linkem Bildschirm")
        self.assertEqual(res["action"], "move_window")
        self.assertEqual(res["target"], "__active_window__")
        self.assertEqual(res["monitor"], 0)

        res = parse_command("schiebe es auf Arbeitsfläche 2")
        self.assertEqual(res["action"], "move_window")
        self.assertEqual(res["target"], "__active_window__")
        self.assertEqual(res["desktop"], 1)

        res = parse_command("schiebe es zurück")
        self.assertEqual(res["action"], "move_window")
        self.assertEqual(res["target"], "__active_window__")
        self.assertTrue(res["restore_previous"])


class TestTaskParsing(unittest.TestCase):
    def test_create_prefix(self):
        res = parse_command("todo: Steuerunterlagen hochladen")
        self.assertEqual(res["action"], "add_task")
        self.assertEqual(res["task_text"], "Steuerunterlagen hochladen")
        self.assertIsNone(res["task_due"])

    def test_create_with_due_morgen(self):
        from datetime import date, timedelta
        res = parse_command("erinnere mich morgen daran die Rechnung zu zahlen")
        self.assertEqual(res["action"], "add_task")
        self.assertEqual(res["task_due"], (date.today() + timedelta(days=1)).isoformat())
        self.assertEqual(res["task_due_label"], "morgen")

    def test_query_open_tasks(self):
        for cmd in ["was sind meine offenen Aufgaben", "zeig meine Todos", "was muss ich noch erledigen"]:
            res = parse_command(cmd)
            self.assertEqual(res["action"], "query_tasks", cmd)

    def test_complete_by_index(self):
        res = parse_command("erledige Aufgabe 2")
        self.assertEqual(res["action"], "complete_task")
        self.assertEqual(res["task_index"], 2)

    def test_complete_by_text(self):
        res = parse_command("hake die Steuer ab")
        self.assertEqual(res["action"], "complete_task")
        self.assertIn("steuer", res["task_ref"].lower())


class TestKnowledgeQuery(unittest.TestCase):
    def test_search_with_topic(self):
        res = parse_command("was habe ich zu Projekt Phoenix notiert")
        self.assertEqual(res["action"], "query_notes")
        self.assertEqual(res["note_mode"], "search")
        self.assertIn("Phoenix", res["target"])

    def test_summarize_with_time(self):
        res = parse_command("fasse meine Notizen von letzter Woche zusammen")
        self.assertEqual(res["action"], "query_notes")
        self.assertEqual(res["note_mode"], "summarize")
        self.assertEqual(res["time_filter"], "week")


if __name__ == "__main__":
    unittest.main()
