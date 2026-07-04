import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_server
from env_isolation import reset_auth_service_singleton


class TestMobileTimelineDbFirst(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self._db_path = Path(self._tmp.name) / "timeline_db_first.sqlite3"
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
        reset_auth_service_singleton()
        self._tmp.cleanup()

    @patch("web_server._save_profile")
    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    def test_timeline_backfills_profile_rows_into_db_and_reads_db_first(
        self,
        mock_require_user,
        mock_safe_profile,
        _mock_save,
    ):
        profile = {
            "web_timeline": {
                "u1": [
                    {
                        "time": "Now",
                        "event": "Legacy profile timeline row",
                        "status": "ready",
                        "command_id": "legacy_cmd_1",
                    }
                ]
            }
        }
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        first_response = self.client.get("/v1/mobile/timeline")
        self.assertEqual(first_response.status_code, 200)
        first_items = first_response.json().get("items", [])
        self.assertTrue(
            any(
                isinstance(row, dict)
                and "legacy profile timeline row" in str(row.get("event", "")).lower()
                for row in first_items
            )
        )

        db_events = web_server._db_event_repository().get_events_by_user("u1", limit=20)
        self.assertTrue(
            any(
                str(getattr(row, "event_type", "")).lower() == "mobile_timeline_item"
                and "legacy profile timeline row"
                in str((getattr(row, "metadata_json", {}) or {}).get("event", "")).lower()
                for row in db_events
            )
        )

        profile["web_timeline"] = {}
        second_response = self.client.get("/v1/mobile/timeline")
        self.assertEqual(second_response.status_code, 200)
        second_items = second_response.json().get("items", [])
        self.assertTrue(
            any(
                isinstance(row, dict)
                and "legacy profile timeline row" in str(row.get("event", "")).lower()
                for row in second_items
            )
        )


if __name__ == "__main__":
    unittest.main()
