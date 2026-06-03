"""
Security regression tests for the three fixes identified in the audit:
  1. XSS in OAuth callback error rendering (main.py)
  2. Unrestricted file deletion via delete_file (search/executor.py)
  3. Token file world-readable race window (auth/spotify.py, auth/google_calendar.py)
"""
import sys
import os
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Put backend on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

import memory
memory._DB_PATH = os.path.join(tempfile.mkdtemp(), "test_security.db")
memory.init_db()


# ---------------------------------------------------------------------------
# Fix 1: XSS in OAuth callback error rendering
# ---------------------------------------------------------------------------

class TestXSSInOAuthCallbacks(unittest.TestCase):
    """The `error` query-param must be HTML-escaped before embedding in HTMLResponse.

    We call the callback functions directly (they are plain Python functions that
    return HTMLResponse objects) — no HTTP client required.
    """

    def setUp(self):
        import main as _main
        self.spotify_callback = _main.spotify_callback
        self.calendar_callback = _main.calendar_callback

    def _body(self, resp) -> str:
        # HTMLResponse.body is bytes; decode to str for assertions
        return resp.body.decode()

    def _assert_escaped(self, callback_fn, payload: str):
        import html as _html
        resp = callback_fn(error=payload)
        body = self._body(resp)
        self.assertNotIn(payload, body,
                         f"Unescaped payload found in response body: {body[:300]}")
        self.assertIn(_html.escape(payload), body,
                      f"Escaped payload missing from response body: {body[:300]}")

    def test_spotify_script_tag_is_escaped(self):
        self._assert_escaped(self.spotify_callback, "<script>alert('xss')</script>")

    def test_spotify_img_onerror_is_escaped(self):
        self._assert_escaped(self.spotify_callback, "<img src=x onerror=alert(1)>")

    def test_calendar_script_tag_is_escaped(self):
        self._assert_escaped(self.calendar_callback, "<script>alert('xss')</script>")

    def test_calendar_bold_injection_is_escaped(self):
        self._assert_escaped(self.calendar_callback, "<b>bold injection</b>")

    def test_spotify_plain_error_text_still_appears(self):
        """Plain text error values must still be visible after escaping."""
        resp = self.spotify_callback(error="access_denied")
        self.assertIn("access_denied", self._body(resp))

    def test_calendar_plain_error_text_still_appears(self):
        resp = self.calendar_callback(error="access_denied")
        self.assertIn("access_denied", self._body(resp))

    def test_spotify_exception_message_is_escaped(self):
        """exchange_code exceptions are also escaped before rendering."""
        import main as _main
        import html as _html
        import auth.spotify as sp_auth
        payload = "<script>evil()</script>"
        # Generate a valid state so the CSRF check passes; we test the exception path
        sp_auth.get_auth_url()
        valid_state = sp_auth._pending_state
        with patch.object(_main.sp_auth, "exchange_code",
                          side_effect=Exception(payload)):
            resp = self.spotify_callback(code="dummy_code", state=valid_state)
        body = self._body(resp)
        self.assertNotIn(payload, body)
        self.assertIn(_html.escape(payload), body)

    def test_calendar_exception_message_is_escaped(self):
        import main as _main
        import html as _html
        import auth.google_calendar as gc_auth
        payload = "<script>evil()</script>"
        gc_auth.get_auth_url()
        valid_state = gc_auth._pending_state
        with patch.object(_main.gc_auth, "exchange_code",
                          side_effect=Exception(payload)):
            resp = self.calendar_callback(code="dummy_code", state=valid_state)
        body = self._body(resp)
        self.assertNotIn(payload, body)
        self.assertIn(_html.escape(payload), body)


# ---------------------------------------------------------------------------
# Fix 2: Unrestricted file deletion
# ---------------------------------------------------------------------------

class TestRestrictedFileDeletion(unittest.TestCase):
    """delete_file must only remove files inside NOTES_DIR."""

    def setUp(self):
        self._notes_dir = tempfile.mkdtemp()
        # Patch NOTES_DIR used by the executor at import time
        import shared.paths as _paths
        self._orig_notes_dir = _paths.NOTES_DIR
        _paths.NOTES_DIR = Path(self._notes_dir)

        # Re-import executor so it picks up the patched NOTES_DIR
        import importlib
        import capabilities.search.executor as _exec
        importlib.reload(_exec)
        self.executor = _exec

    def tearDown(self):
        import shared.paths as _paths
        _paths.NOTES_DIR = self._orig_notes_dir
        import importlib
        import capabilities.search.executor as _exec
        importlib.reload(_exec)

    # --- paths that MUST be blocked ---

    def test_blocks_absolute_path_outside_notes(self):
        victim = tempfile.NamedTemporaryFile(delete=False)
        victim.close()
        try:
            result = self.executor.delete_file(victim.name)
            self.assertFalse(result["success"])
            self.assertTrue(os.path.exists(victim.name),
                            "File outside NOTES_DIR was deleted!")
        finally:
            try:
                os.unlink(victim.name)
            except OSError:
                pass

    def test_blocks_home_directory_sensitive_files(self):
        home = os.path.expanduser("~")
        for sensitive in [
            os.path.join(home, ".ssh", "id_rsa"),
            os.path.join(home, ".bashrc"),
            "/etc/passwd",
            "/tmp/arbitrary_file",
        ]:
            result = self.executor.delete_file(sensitive)
            self.assertFalse(result["success"],
                             f"Expected failure deleting {sensitive!r}, got success")

    def test_blocks_path_traversal_via_dotdot(self):
        # Construct a path that starts inside NOTES_DIR but escapes via ..
        traversal = os.path.join(self._notes_dir, "..", "escaped_file.txt")
        victim = tempfile.NamedTemporaryFile(
            dir=os.path.dirname(self._notes_dir), delete=False
        )
        victim.close()
        try:
            result = self.executor.delete_file(traversal)
            self.assertFalse(result["success"],
                             "Path traversal via .. was not blocked!")
            self.assertTrue(os.path.exists(victim.name))
        finally:
            try:
                os.unlink(victim.name)
            except OSError:
                pass

    # --- paths that MUST be allowed ---

    def test_allows_note_inside_notes_dir(self):
        note = os.path.join(self._notes_dir, "2025-01-01_test-note.md")
        Path(note).write_text("test content")
        result = self.executor.delete_file(note)
        self.assertTrue(result["success"],
                        f"Should have deleted a note inside NOTES_DIR: {result}")
        self.assertFalse(os.path.exists(note), "Note file still exists after deletion")

    def test_allows_note_in_subdirectory(self):
        subdir = os.path.join(self._notes_dir, "project")
        os.makedirs(subdir, exist_ok=True)
        note = os.path.join(subdir, "sub-note.md")
        Path(note).write_text("sub note content")
        result = self.executor.delete_file(note)
        self.assertTrue(result["success"])
        self.assertFalse(os.path.exists(note))

    def test_missing_note_returns_failure_not_error(self):
        ghost = os.path.join(self._notes_dir, "does-not-exist.md")
        result = self.executor.delete_file(ghost)
        self.assertFalse(result["success"])
        self.assertIn("gefunden" if "gefunden" in result["message"] else "found",
                      result["message"])


# ---------------------------------------------------------------------------
# Fix 3: Token file atomic write — never world-readable
# ---------------------------------------------------------------------------

class TestTokenFilePermissions(unittest.TestCase):
    """Token files must be created with 0o600 and never be world-readable."""

    def _make_token_dir(self):
        return tempfile.mkdtemp()

    # --- Spotify ---

    def test_spotify_token_file_permissions_are_0o600(self):
        import auth.spotify as sp
        token_dir = self._make_token_dir()
        token_file = os.path.join(token_dir, "spotify_tokens.json")
        with patch.object(sp, "TOKEN_FILE", token_file):
            sp._save({"access_token": "test", "expires_at": 9999999999})
        mode = stat.S_IMODE(os.stat(token_file).st_mode)
        self.assertEqual(mode, 0o600,
                         f"Spotify token file has mode {oct(mode)}, expected 0o600")

    def test_spotify_token_file_is_valid_json(self):
        import auth.spotify as sp
        token_dir = self._make_token_dir()
        token_file = os.path.join(token_dir, "spotify_tokens.json")
        tokens = {"access_token": "abc123", "refresh_token": "xyz", "expires_at": 1234}
        with patch.object(sp, "TOKEN_FILE", token_file):
            sp._save(tokens)
        with open(token_file) as f:
            loaded = json.load(f)
        self.assertEqual(loaded["access_token"], "abc123")

    def test_spotify_no_tmp_file_left_behind(self):
        import auth.spotify as sp
        token_dir = self._make_token_dir()
        token_file = os.path.join(token_dir, "spotify_tokens.json")
        with patch.object(sp, "TOKEN_FILE", token_file):
            sp._save({"access_token": "test", "expires_at": 9999999999})
        tmp_files = [f for f in os.listdir(token_dir) if f.endswith(".tmp")]
        self.assertEqual(tmp_files, [], f"Temp files left behind: {tmp_files}")

    def test_spotify_overwrite_preserves_0o600(self):
        import auth.spotify as sp
        token_dir = self._make_token_dir()
        token_file = os.path.join(token_dir, "spotify_tokens.json")
        with patch.object(sp, "TOKEN_FILE", token_file):
            sp._save({"access_token": "first", "expires_at": 1})
            sp._save({"access_token": "second", "expires_at": 2})
        mode = stat.S_IMODE(os.stat(token_file).st_mode)
        self.assertEqual(mode, 0o600)
        with open(token_file) as f:
            self.assertEqual(json.load(f)["access_token"], "second")

    # --- Google Calendar ---

    def test_google_token_file_permissions_are_0o600(self):
        import auth.google_calendar as gc
        token_dir = self._make_token_dir()
        token_file = os.path.join(token_dir, "google_calendar_tokens.json")
        with patch.object(gc, "TOKEN_FILE", token_file):
            gc._save({"access_token": "test", "expires_at": 9999999999})
        mode = stat.S_IMODE(os.stat(token_file).st_mode)
        self.assertEqual(mode, 0o600,
                         f"Google token file has mode {oct(mode)}, expected 0o600")

    def test_google_token_file_is_valid_json(self):
        import auth.google_calendar as gc
        token_dir = self._make_token_dir()
        token_file = os.path.join(token_dir, "google_calendar_tokens.json")
        tokens = {"access_token": "gcal_abc", "refresh_token": "gcal_xyz", "expires_at": 5678}
        with patch.object(gc, "TOKEN_FILE", token_file):
            gc._save(tokens)
        with open(token_file) as f:
            loaded = json.load(f)
        self.assertEqual(loaded["access_token"], "gcal_abc")

    def test_google_no_tmp_file_left_behind(self):
        import auth.google_calendar as gc
        token_dir = self._make_token_dir()
        token_file = os.path.join(token_dir, "google_calendar_tokens.json")
        with patch.object(gc, "TOKEN_FILE", token_file):
            gc._save({"access_token": "test", "expires_at": 9999999999})
        tmp_files = [f for f in os.listdir(token_dir) if f.endswith(".tmp")]
        self.assertEqual(tmp_files, [], f"Temp files left behind: {tmp_files}")

    def test_google_overwrite_preserves_0o600(self):
        import auth.google_calendar as gc
        token_dir = self._make_token_dir()
        token_file = os.path.join(token_dir, "google_calendar_tokens.json")
        with patch.object(gc, "TOKEN_FILE", token_file):
            gc._save({"access_token": "first_gc", "expires_at": 1})
            gc._save({"access_token": "second_gc", "expires_at": 2})
        mode = stat.S_IMODE(os.stat(token_file).st_mode)
        self.assertEqual(mode, 0o600)
        with open(token_file) as f:
            self.assertEqual(json.load(f)["access_token"], "second_gc")


if __name__ == "__main__":
    unittest.main(verbosity=2)
