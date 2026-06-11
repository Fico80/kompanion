import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

import unittest
from parser import _parse_regex as parse_regex, parse_command
from capabilities.browser.query import build_search_query, extract_site_hint
from capabilities.browser.ranker import rank_results
from capabilities.browser.search import SearchResult


def parse_basic_command(text):
    return parse_regex(text)


def rank_only(task, query, site_hint, results):
    result, _score = rank_results(task, query, site_hint, results)
    return result

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

    def test_brightness_spoken_number_percent(self):
        res = parse_command("helligkeit auf fünfzig prozent")
        self.assertEqual(res["action"], "set_brightness")
        self.assertEqual(res["target"], "50%")

        res = parse_command("brightness to twenty five percent")
        self.assertEqual(res["action"], "set_brightness")
        self.assertEqual(res["target"], "25%")


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

    def test_audio_spoken_number_percent(self):
        res = self.assertStage("lautstärke auf fünfzig prozent", "set_volume", "audio")
        self.assertEqual(res["target"], "50%")

        res = self.assertStage("Spotify auf fünfzig Prozent", "set_app_volume", "app_volume")
        self.assertEqual(res["target"], "50%")

        res = self.assertStage("lautstärke auf fünfundzwanzig prozent", "set_volume", "audio")
        self.assertEqual(res["target"], "25%")

    def test_timer_with_duration(self):
        self.assertStage("erinnere mich in 10 Minuten ans Meeting", "set_timer", "timer")

    def test_timer_with_spoken_number_duration(self):
        res = self.assertStage(
            "erinnere mich in zwei Stunden Versicherungsmathematik hausübung abzugeben",
            "set_timer",
            "timer",
        )
        self.assertEqual(res["target"], "7200")
        self.assertEqual(res["timer_label"], "Versicherungsmathematik hausübung abzugeben")

    def test_timer_with_label_before_spoken_number_duration(self):
        res = self.assertStage("erinnere mich an das Meeting in zwei Stunden", "set_timer", "timer")
        self.assertEqual(res["target"], "7200")
        self.assertEqual(res["timer_label"], "das Meeting")

    def test_timer_without_label_does_not_use_duration_as_label(self):
        res = self.assertStage("timer zwei minuten", "set_timer", "timer")
        self.assertEqual(res["target"], "120")
        self.assertEqual(res["timer_label"], "")

    def test_timer_set_timer_prefix_without_label(self):
        res = self.assertStage("set timer two minutes", "set_timer", "timer")
        self.assertEqual(res["target"], "120")
        self.assertEqual(res["timer_label"], "")

    def test_timer_for_duration_without_label(self):
        res = self.assertStage("remind me for two minutes", "set_timer", "timer")
        self.assertEqual(res["target"], "120")
        self.assertEqual(res["timer_label"], "")

    def test_timer_strips_german_label_preposition(self):
        res = self.assertStage("erinnere mich in einer Stunde ans Meeting", "set_timer", "timer")
        self.assertEqual(res["target"], "3600")
        self.assertEqual(res["timer_label"], "Meeting")

    def test_calendar_not_stolen_by_task(self):
        self.assertStage("was steht heute im Kalender", "query_calendar", "kalender")
        self.assertStage("erstelle Termin Zahnarzt morgen um 9 Uhr", "create_calendar_event", "kalender_neu")

    def test_calendar_spoken_number_time(self):
        res = self.assertStage("erstelle termin Zahnarzt morgen um zwei Uhr", "create_calendar_event", "kalender_neu")
        self.assertEqual(res["event_hour"], 2)
        self.assertEqual(res["event_min"], 0)
        self.assertEqual(res["event_name"], "Zahnarzt")

        res = self.assertStage("create meeting tomorrow at two pm", "create_calendar_event", "kalender_neu")
        self.assertEqual(res["event_hour"], 14)
        self.assertEqual(res["event_min"], 0)

    def test_note_creation(self):
        self.assertStage("notiere dass ich Brot kaufen muss", "save_note", "notiz")

    def test_clipboard_not_stolen_by_knowledge(self):
        self.assertStage("fasse das zusammen", "clipboard_task", "clipboard")
        self.assertStage("fasse den Text zusammen", "clipboard_task", "clipboard")

    def test_clipboard_translation_language_normalization(self):
        res = self.assertStage("übersetze das ins Englische", "clipboard_task", "clipboard")
        self.assertEqual(res["target"], "translate_to")
        self.assertEqual(res["clipboard_lang"], "Englisch")

    def test_file_search_not_stolen_by_knowledge(self):
        self.assertStage("suche das PDF in Downloads", "search_files", "suche")
        self.assertStage("finde meine Urlaubsfotos", "search_files", "suche")

    def test_screen_vision(self):
        self.assertStage("was siehst du auf dem Bildschirm", "screen_query", "screen")
        self.assertStage("describe the screen", "screen_query", "screen")

    def test_browser_find(self):
        res = self.assertStage("zeige mir info page über level 100 rex auf dododex", "browser_find", "browser")
        self.assertIn("dododex", res.get("task", "").lower())

    def test_browser_search(self):
        self.assertStage("suche nach pipewire bluetooth rauschen online", "browser_search", "browser")

    def test_weather_language_and_day(self):
        res = self.assertStage("how is the weather tomorrow", "query_weather", "wetter")
        self.assertEqual(res.get("lang"), "en")
        self.assertEqual(res.get("weather_day"), "tomorrow")

        res = self.assertStage("wie ist das wetter morgen", "query_weather", "wetter")
        self.assertEqual(res.get("lang"), "de")
        self.assertEqual(res.get("weather_day"), "tomorrow")

    def test_weather_day_after_tomorrow(self):
        res = self.assertStage("wie wird das wetter übermorgen in Wien", "query_weather", "wetter")
        self.assertEqual(res.get("weather_day"), "day_after_tomorrow")
        self.assertEqual(res.get("target"), "Wien")


class TestBrowserFind(unittest.TestCase):
    def test_query_with_site_hint(self):
        task = "zeige mir info page über level 100 rex auf dododex"
        self.assertEqual(extract_site_hint(task), "dododex")
        self.assertEqual(build_search_query(task, "dododex"), "level 100 rex dododex")

    def test_query_with_domain_hint(self):
        task = "show me qdbus docs on kde.org"
        self.assertEqual(build_search_query(task, "kde.org"), "site:kde.org qdbus docs")

    def test_heuristic_prefers_site_hint(self):
        results = [
            SearchResult(title="Rex - ARK Wiki", url="https://ark.wiki.gg/wiki/Rex", snippet="ARK rex info"),
            SearchResult(title="Rex Taming Calculator", url="https://www.dododex.com/taming/rex", snippet="level calculator"),
        ]
        chosen = rank_only("zeige mir level 100 rex auf dododex", "level 100 rex dododex", "dododex", results)
        self.assertIsNotNone(chosen)
        self.assertIn("dododex.com", chosen.url)

    def test_heuristic_prefers_main_page_over_deep_user_content(self):
        results = [
            SearchResult(
                title="Random Rex tip",
                url="https://www.dododex.com/tips/rex/7639/the-rex-especially-above-lv-100",
                snippet="rex user tip",
            ),
            SearchResult(
                title="Rex | ARK: Survival Ascended & Evolved - Dododex",
                url="https://www.dododex.com/taming/rex",
                snippet="Rex taming calculator, food requirements, saddle ingredients.",
            ),
        ]
        chosen = rank_only("zeige mir rex auf dododex", "rex dododex", "dododex", results)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.url, "https://www.dododex.com/taming/rex")

    def test_heuristic_penalizes_unrequested_product_variants(self):
        results = [
            SearchResult(
                title="Apple iPhone 16 Pro Preisvergleich",
                url="https://www.idealo.de/preisvergleich/OffersOfProduct/123_-iphone-16-pro-apple.html",
                snippet="iPhone 16 Pro Angebote",
            ),
            SearchResult(
                title="Apple iPhone 16 Preisvergleich",
                url="https://www.idealo.de/preisvergleich/OffersOfProduct/456_-iphone-16-apple.html",
                snippet="iPhone 16 Angebote",
            ),
        ]
        chosen = rank_only("zeige mir iphone 16 vergleich auf idealo", "iphone 16 vergleich idealo", "idealo", results)
        self.assertIsNotNone(chosen)
        self.assertIn("iphone-16-apple", chosen.url)

    def test_heuristic_penalizes_wrong_model_numbers(self):
        results = [
            SearchResult(
                title="Apple iPhone 17 Preisvergleich",
                url="https://www.idealo.de/preisvergleich/OffersOfProduct/789_-iphone-17-apple.html",
                snippet="iPhone 17 Angebote",
            ),
            SearchResult(
                title="Apple iPhone 16 Preisvergleich",
                url="https://www.idealo.de/preisvergleich/OffersOfProduct/456_-iphone-16-apple.html",
                snippet="iPhone 16 Angebote",
            ),
        ]
        chosen = rank_only("zeige mir iphone 16 vergleich auf idealo", "iphone 16 vergleich idealo", "idealo", results)
        self.assertIsNotNone(chosen)
        self.assertIn("iphone-16-apple", chosen.url)

    def test_heuristic_penalizes_homepage_for_specific_queries(self):
        results = [
            SearchResult(
                title="idealo - Die Nr. 1 im Preisvergleich",
                url="https://www.idealo.de/",
                snippet="Preisvergleich",
            ),
            SearchResult(
                title="Apple iPhone 16 Preisvergleich",
                url="https://www.idealo.de/preisvergleich/OffersOfProduct/456_-iphone-16-apple.html",
                snippet="iPhone 16 Angebote",
            ),
        ]
        chosen = rank_only("zeige mir iphone 16 vergleich auf idealo", "iphone 16 vergleich idealo", "idealo", results)
        self.assertIsNotNone(chosen)
        self.assertIn("iphone-16-apple", chosen.url)

    def test_heuristic_requires_site_hint_domain_match(self):
        results = [
            SearchResult(
                title="Ventilatoren bei Amazon vergleichen",
                url="https://www.spardeingeld.de/ventilatoren/shops--amazon.de/products.html",
                snippet="Amazon Angebote",
            ),
            SearchResult(
                title="Ventilatoren - Amazon.de",
                url="https://www.amazon.de/Ventilatoren/b?node=3677555031",
                snippet="Ventilatoren kaufen",
            ),
        ]
        chosen = rank_only("zeige mir ventilatoren auf amazon", "ventilatoren amazon", "amazon", results)
        self.assertIsNotNone(chosen)
        self.assertIn("amazon.de", chosen.url)

    def test_heuristic_rejects_brand_word_in_third_party_domain(self):
        results = [
            SearchResult(
                title="idealo price comparison app",
                url="https://idealo-price-comparison-shopping-ios.soft112.com/",
                snippet="Download app",
            ),
            SearchResult(
                title="Apple iPhone 16 Preisvergleich",
                url="https://www.idealo.de/preisvergleich/OffersOfProduct/456_-iphone-16-apple.html",
                snippet="iPhone 16 Angebote",
            ),
        ]
        chosen = rank_only("zeige mir iphone 16 vergleich auf idealo", "iphone 16 vergleich idealo", "idealo", results)
        self.assertIsNotNone(chosen)
        self.assertIn("idealo.de", chosen.url)

    def test_heuristic_prefers_text_tutorial_by_default(self):
        results = [
            SearchResult(
                title="Fire Bow Tutorial #shorts",
                url="https://www.tiktok.com/@player/video/123",
                snippet="Der Eisendrache fire bow tutorial",
            ),
            SearchResult(
                title="Der Eisendrache Fire Bow Guide",
                url="https://example.com/guides/der-eisendrache-fire-bow",
                snippet="Step by step tutorial for the fire bow.",
            ),
        ]
        chosen = rank_only(
            "zeige mir ein tutorial für den feuerbogen auf der eisendrache",
            "tutorial feuerbogen eisendrache",
            None,
            results,
        )
        self.assertIsNotNone(chosen)
        self.assertIn("/guides/", chosen.url)

    def test_heuristic_prefers_video_when_requested(self):
        results = [
            SearchResult(
                title="Fire Bow Tutorial Video",
                url="https://www.youtube.com/watch?v=123",
                snippet="Der Eisendrache fire bow tutorial video",
            ),
            SearchResult(
                title="Der Eisendrache Fire Bow Guide",
                url="https://example.com/guides/der-eisendrache-fire-bow",
                snippet="Step by step tutorial for the fire bow.",
            ),
        ]
        chosen = rank_only(
            "zeige mir ein video tutorial für den feuerbogen auf der eisendrache",
            "video tutorial feuerbogen eisendrache",
            None,
            results,
        )
        self.assertIsNotNone(chosen)
        self.assertIn("youtube.com", chosen.url)

    def test_ranker_uses_general_translation_hints(self):
        results = [
            SearchResult(
                title="Bluetooth speaker review",
                url="https://example.com/speaker-review",
                snippet="Portable speaker comparison",
            ),
            SearchResult(
                title="Bluetooth mouse review",
                url="https://example.com/mouse-review",
                snippet="Computer accessory comparison",
            ),
        ]
        chosen = rank_only(
            "zeige mir bluetooth lautsprecher vergleich",
            "bluetooth lautsprecher vergleich",
            None,
            results,
        )
        self.assertIsNotNone(chosen)
        self.assertIn("speaker", chosen.url)


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

        res = parse_command("verschiebe firefox auf arbeitsfläche zwei")
        self.assertEqual(res["action"], "move_window")
        self.assertEqual(res["target"], "firefox")
        self.assertEqual(res["desktop"], 1)

        res = parse_command("schiebe es auf arbeitsfläche zwei")
        self.assertEqual(res["action"], "move_window")
        self.assertEqual(res["target"], "__active_window__")
        self.assertEqual(res["desktop"], 1)

        res = parse_command("verschiebe firefox von arbeitsfläche eins auf arbeitsfläche zwei")
        self.assertEqual(res["action"], "move_window")
        self.assertEqual(res["target"], "firefox")
        self.assertEqual(res["from_desktop"], 0)
        self.assertEqual(res["desktop"], 1)

        res = parse_command("move firefox to workspace twenty one")
        self.assertEqual(res["action"], "move_window")
        self.assertEqual(res["target"], "firefox")
        self.assertEqual(res["desktop"], 20)

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

    def test_create_with_spoken_number_due_days(self):
        from datetime import date, timedelta
        res = parse_command("erinnere mich in zwei Tagen daran die Rechnung zu zahlen")
        self.assertEqual(res["action"], "add_task")
        self.assertEqual(res["task_due"], (date.today() + timedelta(days=2)).isoformat())
        self.assertEqual(res["task_text"], "die Rechnung zu zahlen")

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
