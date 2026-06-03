"""
Yellow-severity regression tests for the four fixes:

  1. Non-atomic config writes (shortcuts/executor.py)
  2. Deleted-file rows returned by search_notes substring fallback (memory.py)
  3. Spotify play response unchecked (spotify/executor.py)
  4. Home-dir subdirs leaked to cloud LLM (parser.py)
"""
import sys
import os
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

import memory
memory._DB_PATH = os.path.join(tempfile.mkdtemp(), "test_yellow.db")
memory.init_db()


# ---------------------------------------------------------------------------
# Fix 1: Atomic config writes
# ---------------------------------------------------------------------------

class TestAtomicConfigWrites(unittest.TestCase):
    """urls.json and shortcuts.json must never be left half-written after a crash."""

    def _write_json(self, path: str, data: dict) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # --- helpers ---

    def _make_urls_file(self) -> str:
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "urls.json")
        self._write_json(path, {"existing": {"url": "https://example.com", "title": "Example"}})
        return path

    def _make_shortcuts_file(self) -> str:
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "shortcuts.json")
        self._write_json(path, {"work": ["öffne Firefox", "öffne VS Code"]})
        return path

    # --- save_url ---

    def test_save_url_produces_valid_json(self):
        from capabilities.shortcuts import executor as ex
        urls_path = self._make_urls_file()
        parsed = {"target": "github", "url": "https://github.com", "url_title": "GitHub"}
        with patch.object(ex, "URLS_FILE", urls_path):
            result = ex.save_url(parsed, response_lang="en")
        self.assertTrue(result["success"])
        with open(urls_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("github", data)
        self.assertEqual(data["github"]["url"], "https://github.com")

    def test_save_url_no_tmp_file_left_behind(self):
        from capabilities.shortcuts import executor as ex
        urls_path = self._make_urls_file()
        parsed = {"target": "github", "url": "https://github.com", "url_title": "GitHub"}
        with patch.object(ex, "URLS_FILE", urls_path):
            ex.save_url(parsed, response_lang="en")
        dir_ = os.path.dirname(urls_path)
        tmp_files = [f for f in os.listdir(dir_) if f.endswith(".tmp")]
        self.assertEqual(tmp_files, [], f"Temp files left behind: {tmp_files}")

    def test_delete_url_produces_valid_json(self):
        from capabilities.shortcuts import executor as ex
        urls_path = self._make_urls_file()
        with patch.object(ex, "URLS_FILE", urls_path):
            result = ex.delete_url("existing", response_lang="en")
        self.assertTrue(result["success"])
        with open(urls_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertNotIn("existing", data)

    def test_save_shortcut_no_tmp_file_left_behind(self):
        from capabilities.shortcuts import executor as ex
        sc_path = self._make_shortcuts_file()
        parsed = {"target": "morning", "shortcut_commands": ["öffne Firefox", "öffne Spotify"]}
        with patch.object(ex, "SHORTCUTS_FILE", sc_path):
            ex.save_shortcut_desc(parsed, response_lang="en")
        dir_ = os.path.dirname(sc_path)
        tmp_files = [f for f in os.listdir(dir_) if f.endswith(".tmp")]
        self.assertEqual(tmp_files, [], f"Temp files left behind after save_shortcut_desc: {tmp_files}")

    def test_delete_shortcut_produces_valid_json(self):
        from capabilities.shortcuts import executor as ex
        sc_path = self._make_shortcuts_file()
        parsed = {"target": "work"}
        with patch.object(ex, "SHORTCUTS_FILE", sc_path):
            result = ex.delete_shortcut(parsed, response_lang="en")
        self.assertTrue(result["success"])
        with open(sc_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertNotIn("work", data)

    def test_save_url_original_preserved_on_exception(self):
        """If the atomic write fails entirely, the original file must survive intact."""
        from capabilities.shortcuts import executor as ex
        urls_path = self._make_urls_file()
        original = json.loads(Path(urls_path).read_text())

        # Make os.replace raise so the write never completes
        with patch.object(ex, "URLS_FILE", urls_path), \
             patch("os.replace", side_effect=OSError("Simulated failure")):
            try:
                ex.save_url({"target": "new", "url": "https://new.com", "url_title": "New"}, "en")
            except OSError:
                pass

        surviving = json.loads(Path(urls_path).read_text())
        self.assertEqual(surviving, original,
                         "Original file must be intact when atomic write fails")


# ---------------------------------------------------------------------------
# Fix 2: Deleted-file rows excluded from search_notes substring fallback
# ---------------------------------------------------------------------------

class TestSearchNotesSubstringExcludesDeleted(unittest.TestCase):
    """search_notes substring fallback must not return rows whose file no longer exists."""

    def setUp(self):
        with memory._conn() as c:
            c.execute("DELETE FROM notes")
            c.commit()

    def _insert_note(self, content: str, path: str):
        with memory._conn() as c:
            c.execute(
                "INSERT INTO notes (ts, content, path, embedding) VALUES (datetime('now'), ?, ?, NULL)",
                (content, path),
            )
            c.commit()

    def test_existing_file_returned_by_substring_search(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".md", delete=False)
        tmp.write(b"hello world note")
        tmp.close()
        try:
            self._insert_note("hello world note", tmp.name)
            with patch.object(memory, "_get_embedding", return_value=None):
                results = memory.search_notes("hello world")
            paths = [r["path"] for r in results]
            self.assertIn(tmp.name, paths, "Existing file must appear in substring results")
        finally:
            os.unlink(tmp.name)

    def test_deleted_file_excluded_from_substring_search(self):
        """A note whose file has been deleted must NOT appear in substring results."""
        ghost_path = "/tmp/__ghost_note_that_does_not_exist__.md"
        # Ensure it really doesn't exist
        if os.path.exists(ghost_path):
            os.unlink(ghost_path)
        self._insert_note("ghost content unique xyz123", ghost_path)

        with patch.object(memory, "_get_embedding", return_value=None):
            results = memory.search_notes("ghost content unique xyz123")

        paths = [r["path"] for r in results]
        self.assertNotIn(ghost_path, paths,
                         "Deleted file must not appear in substring search results")

    def test_null_path_still_returned(self):
        """Notes with path=NULL (no file) must still be returned (they live only in DB)."""
        self._insert_note("null path note for testing", None)
        with patch.object(memory, "_get_embedding", return_value=None):
            results = memory.search_notes("null path note for testing")
        self.assertTrue(any(r["content"] == "null path note for testing" for r in results),
                        "Notes with NULL path must still appear in search results")


# ---------------------------------------------------------------------------
# Fix 3: Spotify play response must be checked
# ---------------------------------------------------------------------------

class TestSpotifyPlayResponseChecked(unittest.TestCase):
    """control_spotify must surface a failure when the play endpoint returns a non-2xx status."""

    def _make_mock_response(self, status_code: int) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        resp.raise_for_status = MagicMock()
        return resp

    def _make_search_response(self, result_type: str, uri: str, name: str) -> MagicMock:
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        if result_type == "track":
            resp.json.return_value = {
                "tracks": {"items": [{"uri": uri, "name": name, "artists": [{"name": "Artist"}]}]}
            }
        elif result_type == "playlist":
            resp.json.return_value = {
                "playlists": {"items": [{"uri": uri, "name": name}]}
            }
        elif result_type == "artist":
            resp.json.return_value = {
                "artists": {"items": [{"uri": uri, "name": name}]}
            }
        return resp

    def _run(self, search_type: str, play_status: int, response_lang: str = "en"):
        from capabilities.spotify import executor as sp_exec
        import auth.spotify as sa

        uri = f"spotify:{search_type}:abc123"
        search_resp = self._make_search_response(search_type, uri, f"Test {search_type.capitalize()}")
        play_resp = self._make_mock_response(play_status)

        call_count = [0]

        def fake_request(method, endpoint, **kwargs):
            if method == "GET" and endpoint == "/me/player/devices":
                dev_resp = MagicMock()
                dev_resp.status_code = 200
                dev_resp.json.return_value = {"devices": [{"id": "dev1", "is_active": True, "type": "Computer"}]}
                return dev_resp
            if method == "GET" and endpoint == "/search":
                return search_resp
            if method == "PUT" and endpoint == "/me/player/play":
                call_count[0] += 1
                return play_resp
            r = MagicMock()
            r.status_code = 200
            return r

        with patch.object(sa, "is_authenticated", return_value=True), \
             patch.object(sa, "request", side_effect=fake_request):
            result = sp_exec.control_spotify(
                f"search_{search_type}", query=f"test {search_type}", response_lang=response_lang
            )

        return result, call_count[0]

    # --- track ---

    def test_track_play_204_success(self):
        result, calls = self._run("track", 204)
        self.assertTrue(result["success"], f"204 must succeed: {result}")
        self.assertEqual(calls, 1)

    def test_track_play_403_returns_failure(self):
        result, calls = self._run("track", 403)
        self.assertFalse(result["success"], f"403 must fail: {result}")
        self.assertIn("403", result["message"])

    def test_track_play_404_returns_failure(self):
        result, _ = self._run("track", 404)
        self.assertFalse(result["success"])
        self.assertIn("404", result["message"])

    # --- playlist ---

    def test_playlist_play_204_success(self):
        result, _ = self._run("playlist", 204)
        self.assertTrue(result["success"])

    def test_playlist_play_403_returns_failure(self):
        result, _ = self._run("playlist", 403)
        self.assertFalse(result["success"])
        self.assertIn("403", result["message"])

    # --- artist ---

    def test_artist_play_204_success(self):
        result, _ = self._run("artist", 204)
        self.assertTrue(result["success"])

    def test_artist_play_403_returns_failure(self):
        result, _ = self._run("artist", 403)
        self.assertFalse(result["success"])
        self.assertIn("403", result["message"])

    def test_play_error_message_german(self):
        result, _ = self._run("track", 403, response_lang="de")
        self.assertFalse(result["success"])
        self.assertIn("403", result["message"])
        self.assertIn("Spotify", result["message"])


# ---------------------------------------------------------------------------
# Fix 4: Home-dir subdirs not sent to LLM
# ---------------------------------------------------------------------------

class TestHomeFolderSubdirs(unittest.TestCase):
    """_scan_home_folders hides subdirs for cloud LLMs, includes them for local ones."""

    def _run_scan(self, home_structure: dict, include_subdirs: bool) -> str:
        import parser as _parser
        with tempfile.TemporaryDirectory() as fake_home:
            for top, subdirs in home_structure.items():
                os.makedirs(os.path.join(fake_home, top))
                for sub in subdirs:
                    os.makedirs(os.path.join(fake_home, top, sub))
            with patch.object(_parser, "HOME", fake_home):
                return _parser._scan_home_folders(include_subdirs=include_subdirs)

    # --- cloud mode (include_subdirs=False) ---

    def test_cloud_top_level_included(self):
        result = self._run_scan({"Documents": [], "Projects": ["web", "api"], "Music": []}, False)
        self.assertIn("Documents", result)
        self.assertIn("Projects", result)
        self.assertIn("Music", result)

    def test_cloud_subdir_names_hidden(self):
        result = self._run_scan({"Projects": ["secret-client", "personal-diary", "work-api"]}, False)
        for subdir in ["secret-client", "personal-diary", "work-api"]:
            self.assertNotIn(subdir, result,
                             f"Cloud mode must not expose subdir '{subdir}'")

    def test_cloud_subdirs_keyword_absent(self):
        result = self._run_scan({"Projects": ["a", "b", "c"]}, False)
        self.assertNotIn("subdirs", result)

    # --- local mode (include_subdirs=True) ---

    def test_local_top_level_included(self):
        result = self._run_scan({"Projects": ["web", "api"]}, True)
        self.assertIn("Projects", result)

    def test_local_subdir_names_present(self):
        result = self._run_scan({"Projects": ["web", "api"]}, True)
        self.assertIn("web", result)
        self.assertIn("api", result)
        self.assertIn("subdirs", result)

    # --- shared behaviour ---

    def test_dotdirs_always_excluded(self):
        for include in (False, True):
            result = self._run_scan({".hidden": [], "Visible": []}, include)
            self.assertNotIn(".hidden", result)
            self.assertIn("Visible", result)

    def test_skip_dirs_always_excluded(self):
        for include in (False, True):
            result = self._run_scan({"snap": ["bin"], "venv": [], "Projects": []}, include)
            self.assertNotIn("snap", result)
            self.assertNotIn("venv", result)
            self.assertIn("Projects", result)

    # --- _is_local_llm URL detection ---

    def test_localhost_detected_as_local(self):
        import parser as _parser
        for url in ("http://localhost:11434", "http://127.0.0.1:8080/v1", "http://0.0.0.0:5000"):
            self.assertTrue(_parser._is_local_llm(url), f"{url!r} should be local")

    def test_cloud_url_not_local(self):
        import parser as _parser
        for url in ("https://integrate.api.nvidia.com/v1", "https://api.openai.com/v1"):
            self.assertFalse(_parser._is_local_llm(url), f"{url!r} should not be local")


if __name__ == "__main__":
    unittest.main(verbosity=2)
