import os
import stat
import sys
import tempfile
import types
import unittest
from datetime import date
from io import StringIO
from unittest import mock

# Import from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import thunderbird_schedule as ts  # noqa: E402


class FakeCreds:
    """Picklable stand-in for google.oauth2.credentials.Credentials."""
    valid = True
    expired = False
    refresh_token = None


def fake_google_modules():
    """Return sys.modules entries that stand in for the Google API libraries."""
    flow = types.SimpleNamespace(run_local_server=lambda port: FakeCreds())
    insert = mock.Mock()
    insert.return_value.execute.return_value = {}
    service = types.SimpleNamespace(events=lambda: types.SimpleNamespace(insert=insert))

    modules = {}
    for name in ("google", "google.oauth2", "google.oauth2.credentials", "google.auth",
                 "google.auth.transport", "google.auth.transport.requests", "google_auth_oauthlib",
                 "google_auth_oauthlib.flow", "googleapiclient", "googleapiclient.discovery"):
        modules[name] = types.ModuleType(name)
    modules["google.oauth2.credentials"].Credentials = object
    modules["google.auth.transport.requests"].Request = object
    modules["google_auth_oauthlib.flow"].InstalledAppFlow = types.SimpleNamespace(
        from_client_secrets_file=lambda path, scopes: flow)
    modules["googleapiclient.discovery"].build = lambda *args, **kwargs: service
    return modules


class TestTokenFilePermissions(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        for patcher in (
            mock.patch.dict(os.environ, {"HOME": self.home.name}),
            mock.patch.dict(sys.modules, fake_google_modules()),
            mock.patch.object(sys, "stderr", StringIO()),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        # A permissive umask, so a plain open() would create a group/world-readable file
        old_umask = os.umask(0o002)
        self.addCleanup(os.umask, old_umask)

        self.token_file = os.path.join(self.home.name, ".thunderbird-schedule-token.pickle")
        with open(os.path.join(self.home.name, ".thunderbird-schedule-credentials.json"), "w") as f:
            f.write("{}")

    def write(self):
        schedule = ts.generate_schedule("desktop", 146, date(2025, 10, 16))
        ts.write_to_google_calendar(schedule, "desktop", 146, "calendar-id")

    def mode(self):
        return stat.S_IMODE(os.stat(self.token_file).st_mode)

    def test_new_token_file_is_owner_only(self):
        self.write()
        self.assertEqual(self.mode(), 0o600)

    def test_existing_loose_token_file_is_tightened(self):
        # An unusable token from an older version, saved world-readable
        with open(self.token_file, "wb") as f:
            f.write(b"")
        os.chmod(self.token_file, 0o664)
        with mock.patch("pickle.load", return_value=None):
            self.write()
        self.assertEqual(self.mode(), 0o600)


if __name__ == "__main__":
    unittest.main()
