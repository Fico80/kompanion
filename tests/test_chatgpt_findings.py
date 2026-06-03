"""
Regression tests for the three fixes from the independent audit:

  A. SQLite connection not closed after use (memory.py)
  B. OAuth CSRF — no state parameter (auth/spotify.py, auth/google_calendar.py, main.py)
  C. Sensitive file permissions enforced at startup (main.py)
"""
import sys
import os
import stat
import tempfile
import threading
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

import memory
memory._DB_PATH = os.path.join(tempfile.mkdtemp(), "test_chatgpt.db")
memory.init_db()


# ---------------------------------------------------------------------------
# Fix A: SQLite connections must be closed after every _conn() call
# ---------------------------------------------------------------------------

class TestSQLiteConnectionClosed(unittest.TestCase):
    """Every _conn() context manager exit must close the underlying connection."""

    def test_connection_is_closed_after_with_block(self):
        """The connection object must report closed after the with block exits."""
        conn_ref = []
        with memory._conn() as c:
            conn_ref.append(c)
        # sqlite3 connections expose a private attribute; closed connections have it set
        # The simplest cross-version check: attempting to execute after close raises ProgrammingError
        with self.assertRaises(Exception):
            conn_ref[0].execute("SELECT 1")

    def test_no_resource_warnings_on_db_operations(self):
        """No ResourceWarning must be emitted when using _conn() for a read operation."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            memory.get_stats()   # read-only, exercises _conn()
        resource_warnings = [w for w in caught if issubclass(w.category, ResourceWarning)]
        self.assertEqual(resource_warnings, [],
                         f"ResourceWarnings emitted: {[str(w.message) for w in resource_warnings]}")

    def test_connection_closed_on_exception(self):
        """Even if an exception is raised inside the with block, the connection must be closed."""
        conn_ref = []
        try:
            with memory._conn() as c:
                conn_ref.append(c)
                raise RuntimeError("simulated failure")
        except RuntimeError:
            pass
        with self.assertRaises(Exception):
            conn_ref[0].execute("SELECT 1")

    def test_concurrent_operations_each_get_own_connection(self):
        """Multiple threads must each open and close their own connection independently."""
        errors = []

        def worker():
            try:
                memory.get_stats()  # opens and closes a connection
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Thread errors: {errors}")


# ---------------------------------------------------------------------------
# Fix B: OAuth state parameter — CSRF protection
# ---------------------------------------------------------------------------

class TestOAuthStateSpotify(unittest.TestCase):
    """Spotify OAuth must include a state parameter and verify it in the callback."""

    def setUp(self):
        import auth.spotify as sp
        sp._pending_state = None  # reset between tests

    def test_get_auth_url_includes_state(self):
        import auth.spotify as sp
        url = sp.get_auth_url()
        self.assertIn("state=", url, "Auth URL must include a state parameter")

    def test_state_is_random_on_each_call(self):
        import auth.spotify as sp
        url1 = sp.get_auth_url()
        url2 = sp.get_auth_url()
        # Extract state values
        state1 = [p.split("=", 1)[1] for p in url1.split("&") if p.startswith("state=")][0]
        state2 = [p.split("=", 1)[1] for p in url2.split("&") if p.startswith("state=")][0]
        self.assertNotEqual(state1, state2, "State must be different on each login attempt")

    def test_verify_state_succeeds_with_correct_value(self):
        import auth.spotify as sp
        sp.get_auth_url()  # sets _pending_state
        state = sp._pending_state
        self.assertTrue(sp.verify_state(state))

    def test_verify_state_fails_with_wrong_value(self):
        import auth.spotify as sp
        sp.get_auth_url()
        self.assertFalse(sp.verify_state("wrong-state-value"))

    def test_verify_state_fails_with_empty_string(self):
        import auth.spotify as sp
        sp.get_auth_url()
        self.assertFalse(sp.verify_state(""))

    def test_verify_state_is_one_time_use(self):
        """State must be consumed after the first verify call — replay must fail."""
        import auth.spotify as sp
        sp.get_auth_url()
        state = sp._pending_state
        sp.verify_state(state)          # first use — consumes the state
        self.assertFalse(sp.verify_state(state), "State must not be reusable after first verify")

    def test_verify_state_fails_without_prior_get_auth_url(self):
        """If no auth URL was generated yet, any state must be rejected."""
        import auth.spotify as sp
        sp._pending_state = None
        self.assertFalse(sp.verify_state("some-state"))

    def test_callback_rejects_wrong_state(self):
        """The /spotify/callback endpoint must return 400 when state doesn't match."""
        import main as _main
        import auth.spotify as sp
        sp.get_auth_url()  # sets _pending_state
        resp = _main.spotify_callback(code="dummy_code", state="bad-state")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("CSRF", resp.body.decode())

    def test_callback_accepts_correct_state(self):
        """The /spotify/callback endpoint must accept the correct state."""
        import main as _main
        import auth.spotify as sp
        sp.get_auth_url()
        state = sp._pending_state
        with patch.object(sp, "exchange_code", return_value={}):
            resp = _main.spotify_callback(code="dummy_code", state=state)
        self.assertNotEqual(resp.status_code, 400)


class TestOAuthStateGoogleCalendar(unittest.TestCase):
    """Google Calendar OAuth must include a state parameter and verify it in the callback."""

    def setUp(self):
        import auth.google_calendar as gc
        gc._pending_state = None

    def test_get_auth_url_includes_state(self):
        import auth.google_calendar as gc
        url = gc.get_auth_url()
        self.assertIn("state=", url)

    def test_state_is_random_on_each_call(self):
        import auth.google_calendar as gc
        url1 = gc.get_auth_url()
        url2 = gc.get_auth_url()
        state1 = [p.split("=", 1)[1] for p in url1.split("&") if p.startswith("state=")][0]
        state2 = [p.split("=", 1)[1] for p in url2.split("&") if p.startswith("state=")][0]
        self.assertNotEqual(state1, state2)

    def test_verify_state_succeeds_with_correct_value(self):
        import auth.google_calendar as gc
        gc.get_auth_url()
        state = gc._pending_state
        self.assertTrue(gc.verify_state(state))

    def test_verify_state_fails_with_wrong_value(self):
        import auth.google_calendar as gc
        gc.get_auth_url()
        self.assertFalse(gc.verify_state("attacker-state"))

    def test_verify_state_is_one_time_use(self):
        import auth.google_calendar as gc
        gc.get_auth_url()
        state = gc._pending_state
        gc.verify_state(state)
        self.assertFalse(gc.verify_state(state))

    def test_callback_rejects_wrong_state(self):
        import main as _main
        import auth.google_calendar as gc
        gc.get_auth_url()
        resp = _main.calendar_callback(code="dummy_code", state="bad-state")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("CSRF", resp.body.decode())

    def test_callback_accepts_correct_state(self):
        import main as _main
        import auth.google_calendar as gc
        gc.get_auth_url()
        state = gc._pending_state
        with patch.object(gc, "exchange_code", return_value={}):
            resp = _main.calendar_callback(code="dummy_code", state=state)
        self.assertNotEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# Fix C: Sensitive file permissions enforced at startup
# ---------------------------------------------------------------------------

class TestSensitiveFilePermissions(unittest.TestCase):
    """`_secure_sensitive_files` must chmod world-readable files to 0o600/0o700."""

    def _make_world_readable_file(self, suffix=".json") -> str:
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        os.chmod(path, 0o644)  # world-readable
        return path

    def _make_world_readable_dir(self) -> str:
        path = tempfile.mkdtemp()
        os.chmod(path, 0o755)  # group+other readable
        return path

    def test_world_readable_file_gets_chmod_600(self):
        import main as _main
        path = self._make_world_readable_file()
        try:
            with patch.object(_main, "ENV_FILE", Path(path)), \
                 patch.object(_main, "MEMORY_DB", Path("/nonexistent")), \
                 patch.object(_main, "DATA_DIR", Path("/nonexistent")):
                _main._secure_sensitive_files()
            mode = stat.S_IMODE(os.stat(path).st_mode)
            self.assertEqual(mode, 0o600,
                             f"World-readable file must be chmod'd to 0o600, got {oct(mode)}")
        finally:
            os.unlink(path)

    def test_already_private_file_not_changed(self):
        """A file already at 0o600 must not be touched."""
        import main as _main
        path = self._make_world_readable_file()
        os.chmod(path, 0o600)
        original_mtime = os.stat(path).st_mtime
        try:
            with patch.object(_main, "ENV_FILE", Path(path)), \
                 patch.object(_main, "MEMORY_DB", Path("/nonexistent")), \
                 patch.object(_main, "DATA_DIR", Path("/nonexistent")):
                _main._secure_sensitive_files()
            # Permissions should still be 0o600
            mode = stat.S_IMODE(os.stat(path).st_mode)
            self.assertEqual(mode, 0o600)
        finally:
            os.unlink(path)

    def test_world_readable_dir_gets_chmod_700(self):
        import main as _main
        path = self._make_world_readable_dir()
        try:
            with patch.object(_main, "DATA_DIR", Path(path)), \
                 patch.object(_main, "ENV_FILE", Path("/nonexistent")), \
                 patch.object(_main, "MEMORY_DB", Path("/nonexistent")):
                _main._secure_sensitive_files()
            mode = stat.S_IMODE(os.stat(path).st_mode)
            self.assertEqual(mode, 0o700,
                             f"World-readable dir must be chmod'd to 0o700, got {oct(mode)}")
        finally:
            os.rmdir(path)

    def test_nonexistent_paths_do_not_raise(self):
        """_secure_sensitive_files must not crash if a sensitive file doesn't exist yet."""
        import main as _main
        with patch.object(_main, "ENV_FILE", Path("/nonexistent/.env")), \
             patch.object(_main, "MEMORY_DB", Path("/nonexistent/memory.db")), \
             patch.object(_main, "DATA_DIR", Path("/nonexistent/data")):
            try:
                _main._secure_sensitive_files()
            except Exception as e:
                self.fail(f"_secure_sensitive_files raised on nonexistent path: {e}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
