import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_server


class TestMobileTimelineDbEvents(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmp.name) / "timeline_events.sqlite3"
        self._env_patch = patch.dict(
            os.environ,
            {"DATABASE_URL": f"sqlite:///{self._db_path.as_posix()}"},
            clear=False,
        )
        self._env_patch.start()
        web_server._DB_CONNECTION = None
        web_server._DB_CONNECTION_URL = ""
        web_server._DB_USER_REPOSITORY = None
        web_server._SUBSCRIPTION_GATE = None
        web_server._DB_BETA_PROGRESS_REPOSITORY = None
        web_server._DB_EVENT_REPOSITORY = None
        web_server._DB_SLEEP_SESSION_REPOSITORY = None
        web_server._DB_COMMAND_REPOSITORY = None
        self.client = TestClient(web_server.app)

    def tearDown(self):
        connection = getattr(web_server, "_DB_CONNECTION", None)
        if connection is not None:
            engine = getattr(connection, "engine", None)
            if engine is not None:
                try:
                    engine.dispose()
                except Exception:
                    pass
        web_server._DB_CONNECTION = None
        web_server._DB_CONNECTION_URL = ""
        web_server._DB_USER_REPOSITORY = None
        web_server._SUBSCRIPTION_GATE = None
        web_server._DB_BETA_PROGRESS_REPOSITORY = None
        web_server._DB_EVENT_REPOSITORY = None
        web_server._DB_SLEEP_SESSION_REPOSITORY = None
        web_server._DB_COMMAND_REPOSITORY = None
        self._env_patch.stop()
        self._tmp.cleanup()

    @patch("web_server._save_profile")
    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    def test_winddown_command_persists_db_timeline_rows(
        self,
        mock_require_user,
        mock_safe_profile,
        _mock_save,
    ):
        profile: dict = {}
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        command_response = self.client.post("/v1/mobile/device-commands", json={"action": "winddown"})
        self.assertEqual(command_response.status_code, 200)

        events = web_server._db_event_repository().get_events_by_user("u1", limit=20)
        timeline_events = [row for row in events if str(getattr(row, "event_type", "")).lower() == "mobile_timeline_item"]
        self.assertTrue(
            any(
                "wind-down routine armed" in str((row.metadata_json or {}).get("event", "")).lower()
                for row in timeline_events
            )
        )

        profile["web_timeline"] = {}
        feed_response = self.client.get("/v1/mobile/timeline")
        self.assertEqual(feed_response.status_code, 200)
        rows = feed_response.json().get("items", [])
        self.assertTrue(
            any(
                "wind-down routine armed" in str(row.get("event", "")).lower()
                for row in rows
                if isinstance(row, dict)
            )
        )


if __name__ == "__main__":
    unittest.main()
