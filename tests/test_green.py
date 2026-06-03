"""
Green-severity regression tests for the four fixes:

  5. Embedding env var: _get_embedding checks LLM_API_KEY, not only NVIDIA_NIM_API_KEY (memory.py)
  6. _load_apps / _load_urls cached with mtime invalidation (shared/config.py)
  7. Fuzzy home-dir match uses word boundary, not bare substring (parser.py)
  8. Unique KWin plugin names for close_app / close_all_windows (windows/executor.py)
"""
import sys
import os
import json
import re
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

import memory
memory._DB_PATH = os.path.join(tempfile.mkdtemp(), "test_green.db")
memory.init_db()


# ---------------------------------------------------------------------------
# Fix 5: _get_embedding must respect LLM_API_KEY
# ---------------------------------------------------------------------------

class TestEmbeddingEnvVar(unittest.TestCase):
    """_get_embedding must use only LLM_API_KEY; NVIDIA_NIM_API_KEY is no longer a fallback."""

    def _fake_embed_endpoint(self, *args, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
        return resp

    def test_llm_api_key_enables_embedding(self):
        """When only LLM_API_KEY is set, _get_embedding must succeed."""
        env = {"LLM_API_KEY": "test-key-llm", "NVIDIA_NIM_API_KEY": ""}
        with patch.dict(os.environ, env, clear=True), \
             patch.object(memory, "_EMBED_URL", "https://example.test/v1/embeddings"), \
             patch("requests.post", side_effect=self._fake_embed_endpoint) as mock_post:
            result = memory._get_embedding("hello world")
        self.assertIsNotNone(result, "_get_embedding must return a vector when LLM_API_KEY is set")
        self.assertEqual(result, [0.1, 0.2, 0.3])
        # The key used in the Authorization header must be the LLM_API_KEY value
        headers = mock_post.call_args.kwargs.get("headers") or mock_post.call_args[1].get("headers", {})
        self.assertIn("test-key-llm", headers.get("Authorization", ""))

    def test_nvidia_nim_key_alone_does_not_work(self):
        """NVIDIA_NIM_API_KEY alone must NOT trigger an embedding call — use LLM_API_KEY instead."""
        env = {"LLM_API_KEY": "", "NVIDIA_NIM_API_KEY": "nvidia-key"}
        with patch.dict(os.environ, env, clear=True), \
             patch.object(memory, "_EMBED_URL", "https://example.test/v1/embeddings"), \
             patch("requests.post") as mock_post:
            result = memory._get_embedding("hello world")
        self.assertIsNone(result, "NVIDIA_NIM_API_KEY alone must not be used — set LLM_API_KEY")
        mock_post.assert_not_called()

    def test_no_key_returns_none(self):
        """With both keys absent, _get_embedding must return None (no API call)."""
        env = {"LLM_API_KEY": "", "NVIDIA_NIM_API_KEY": ""}
        with patch.dict(os.environ, env, clear=True), \
             patch.object(memory, "_EMBED_URL", "https://example.test/v1/embeddings"), \
             patch("requests.post") as mock_post:
            result = memory._get_embedding("test")
        self.assertIsNone(result)
        mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# Fix 6: _load_apps / _load_urls must be cached (mtime invalidation)
# ---------------------------------------------------------------------------

class TestConfigFileCaching(unittest.TestCase):
    """_load_apps and _load_urls must read from disk only when the file has changed."""

    def _make_json_file(self, data: dict) -> str:
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        return path

    def _reset_cache(self):
        import shared.config as cfg
        cfg._apps_cache = None
        cfg._apps_mtime = 0.0
        cfg._urls_cache = None
        cfg._urls_mtime = 0.0

    def setUp(self):
        self._reset_cache()

    def tearDown(self):
        # Must also clean up after the last test so subsequent test files see a clean slate
        self._reset_cache()

    def test_load_apps_reads_file_on_first_call(self):
        import shared.config as cfg
        path = self._make_json_file({"firefox": {"cmd": "firefox"}})
        with patch.object(cfg, "APPS_FILE", path):
            result = cfg._load_apps()
        self.assertIn("firefox", result)

    def test_load_apps_normalizes_alias_keys_to_lowercase(self):
        import shared.config as cfg
        path = self._make_json_file({"Anti Gravity": {"cmd": "antigravity", "name": "Antigravity"}})
        with patch.object(cfg, "APPS_FILE", path):
            result = cfg._load_apps()
        self.assertIn("anti gravity", result)
        self.assertNotIn("Anti Gravity", result)
        self.assertEqual(result["anti gravity"]["name"], "Antigravity")

    def test_load_apps_returns_cached_on_repeated_call(self):
        """Second call with no file change must not re-open the file."""
        import shared.config as cfg
        path = self._make_json_file({"firefox": {"cmd": "firefox"}})
        open_calls = []
        real_open = open

        def counting_open(p, *args, **kwargs):
            if p == path:
                open_calls.append(p)
            return real_open(p, *args, **kwargs)

        with patch.object(cfg, "APPS_FILE", path), \
             patch("builtins.open", side_effect=counting_open):
            cfg._load_apps()  # first call → reads file
            cfg._load_apps()  # second call → should use cache

        self.assertEqual(len(open_calls), 1,
                         "File must be read only once when mtime hasn't changed")

    def test_load_apps_invalidates_cache_when_file_changes(self):
        """Cache must be invalidated when the file's mtime changes."""
        import shared.config as cfg
        path = self._make_json_file({"firefox": {"cmd": "firefox"}})
        with patch.object(cfg, "APPS_FILE", path):
            result1 = cfg._load_apps()
            self.assertIn("firefox", result1)

            # Overwrite the file — ensure mtime differs (sleep 1ms + utime trick)
            time.sleep(0.01)
            new_data = {"vscode": {"cmd": "code"}}
            with open(path, "w") as f:
                json.dump(new_data, f)
            # Touch to ensure mtime is definitely different
            os.utime(path, None)

            result2 = cfg._load_apps()

        self.assertNotIn("firefox", result2)
        self.assertIn("vscode", result2, "Cache must refresh after file changes")

    def test_load_urls_cached(self):
        import shared.config as cfg
        path = self._make_json_file({"google": {"url": "https://google.com"}})
        open_calls = []
        real_open = open

        def counting_open(p, *args, **kwargs):
            if p == path:
                open_calls.append(p)
            return real_open(p, *args, **kwargs)

        with patch.object(cfg, "URLS_FILE", path), \
             patch("builtins.open", side_effect=counting_open):
            cfg._load_urls()
            cfg._load_urls()

        self.assertEqual(len(open_calls), 1, "URLs file must be read only once per mtime epoch")

    def test_load_urls_normalizes_alias_keys_to_lowercase(self):
        import shared.config as cfg
        path = self._make_json_file({"GoStudent": {"url": "https://example.com", "title": "GoStudent"}})
        with patch.object(cfg, "URLS_FILE", path):
            result = cfg._load_urls()
        self.assertIn("gostudent", result)
        self.assertNotIn("GoStudent", result)
        self.assertEqual(result["gostudent"]["title"], "GoStudent")

    def test_load_apps_returns_stale_cache_on_read_error(self):
        """If the file is temporarily unreadable, the last known cache must be returned."""
        import shared.config as cfg
        path = self._make_json_file({"firefox": {"cmd": "firefox"}})
        with patch.object(cfg, "APPS_FILE", path):
            cfg._load_apps()  # populate cache

        # Now make the file unreadable (simulate error)
        with patch.object(cfg, "APPS_FILE", "/nonexistent/apps.json"):
            result = cfg._load_apps()

        self.assertIn("firefox", result, "Stale cache must be returned on read error")


# ---------------------------------------------------------------------------
# Fix 7: Fuzzy home-dir match — word boundary, not substring
# ---------------------------------------------------------------------------

class TestFuzzyHomeDirWordBoundary(unittest.TestCase):
    """The fuzzy home-dir match must use word boundaries, not bare substring matching."""

    def _run_parse_path(self, command: str, home_dirs: list[str]) -> dict:
        """
        Run _parse_regex against a fake home with the given top-level dirs.
        Mocks _load_apps and _load_urls to return empty dicts so only the
        fuzzy home-dir branch is exercised.
        """
        import parser as _parser

        with tempfile.TemporaryDirectory() as fake_home:
            for d in home_dirs:
                os.makedirs(os.path.join(fake_home, d))

            with patch.object(_parser, "HOME", fake_home), \
                 patch.object(_parser, "_load_apps", return_value={}), \
                 patch.object(_parser, "_load_urls", return_value={}):
                result = _parser._parse_regex(command)

        return result

    def test_exact_word_match_succeeds(self):
        """'öffne Projects' must match ~/Projects."""
        result = self._run_parse_path("öffne Projects", ["Projects", "Downloads"])
        self.assertIsNotNone(result)
        self.assertIn("Projects", result.get("target", ""))

    def test_prefix_substring_does_not_match(self):
        """'pro' must NOT match ~/Projects."""
        result = self._run_parse_path("öffne pro ordner", ["Projects"])
        # If a result is returned, it must not be ~/Projects
        if result and result.get("action") == "open_path":
            self.assertNotIn("Projects", result.get("target", ""),
                             "'pro' must not fuzzy-match ~/Projects")

    def test_partial_word_does_not_match(self):
        """'uni' inside 'Kommunikation' must not match ~/Uni."""
        result = self._run_parse_path("Kommunikation", ["Uni", "Downloads"])
        if result and result.get("action") == "open_path":
            self.assertNotIn("Uni", result.get("target", ""),
                             "'uni' inside 'Kommunikation' must not match ~/Uni")

    def test_full_name_with_surrounding_words_matches(self):
        """'meine Uni Sachen' must still match ~/Uni."""
        result = self._run_parse_path("öffne meine Uni Sachen", ["Uni", "Downloads"])
        self.assertIsNotNone(result)
        if result:
            self.assertIn("Uni", result.get("target", ""),
                          "'Uni' as a standalone word must still match ~/Uni")

    def test_longer_match_preferred(self):
        """When both ~/Uni and ~/Universität match, the longer one wins."""
        result = self._run_parse_path("öffne Universität Ordner", ["Uni", "Universität"])
        if result and result.get("action") == "open_path":
            self.assertIn("Universität", result.get("target", ""),
                          "Longer matching dir must be preferred")


# ---------------------------------------------------------------------------
# Fix 8: Unique KWin plugin names (no hardcoded names that can collide)
# ---------------------------------------------------------------------------

class TestUniqueKWinPluginNames(unittest.TestCase):
    """close_app and close_all_windows must use unique plugin names to avoid D-Bus collisions."""

    def _captured_plugin_names(self, fn, *args, **kwargs):
        """Call fn(*args) with load_and_run_kwin_script mocked; return list of plugin names used."""
        import kwin_client
        names = []

        def fake_load(js, name):
            names.append(name)
            return True

        with patch.object(kwin_client, "load_and_run_kwin_script", side_effect=fake_load):
            fn(*args, **kwargs)

        return names

    def test_close_app_uses_unique_name_each_call(self):
        from capabilities.windows.executor import close_app
        names1 = self._captured_plugin_names(close_app, "firefox", "Firefox")
        names2 = self._captured_plugin_names(close_app, "firefox", "Firefox")
        self.assertEqual(len(names1), 1)
        self.assertEqual(len(names2), 1)
        self.assertNotEqual(names1[0], names2[0],
                            "Two consecutive close_app calls must use different plugin names")

    def test_close_all_windows_uses_unique_name_each_call(self):
        from capabilities.windows.executor import close_all_windows
        names1 = self._captured_plugin_names(close_all_windows)
        names2 = self._captured_plugin_names(close_all_windows)
        self.assertEqual(len(names1), 1)
        self.assertEqual(len(names2), 1)
        self.assertNotEqual(names1[0], names2[0],
                            "Two consecutive close_all_windows calls must use different plugin names")

    def test_close_app_plugin_name_contains_prefix(self):
        """Plugin names must still have a recognizable prefix for KWin debugging."""
        from capabilities.windows.executor import close_app
        names = self._captured_plugin_names(close_app, "code", "VS Code")
        self.assertTrue(names[0].startswith("kompanion_"),
                        f"Plugin name '{names[0]}' must start with 'kompanion_'")

    def test_close_all_plugin_name_contains_prefix(self):
        from capabilities.windows.executor import close_all_windows
        names = self._captured_plugin_names(close_all_windows)
        self.assertTrue(names[0].startswith("kompanion_"),
                        f"Plugin name '{names[0]}' must start with 'kompanion_'")

    def test_concurrent_calls_all_use_unique_names(self):
        """10 concurrent close_app calls must each use a distinct plugin name."""
        import threading
        from capabilities.windows.executor import close_app
        import kwin_client

        names = []
        lock = threading.Lock()

        def fake_load(js, name):
            with lock:
                names.append(name)
            return True

        def do_close():
            with patch.object(kwin_client, "load_and_run_kwin_script", side_effect=fake_load):
                close_app("firefox", "Firefox")

        threads = [threading.Thread(target=do_close) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(names), len(set(names)),
                         f"All 10 plugin names must be unique; got duplicates in {names}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
