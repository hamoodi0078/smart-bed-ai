import os
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_server
from env_isolation import reset_auth_service_singleton


class TestMobileSleepSessionsDb(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self._db_path = Path(self._tmp.name) / "sleep_sessions.sqlite3"
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
    def test_winddown_sessions_drive_dashboard_and_beta_metrics(
        self,
        mock_require_user,
        mock_safe_profile,
        _mock_save,
    ):
        profile: dict = {}
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        first = self.client.post("/v1/mobile/device-commands", json={"action": "winddown"})
        self.assertEqual(first.status_code, 200)
        second = self.client.post("/v1/mobile/device-commands", json={"action": "winddown"})
        self.assertEqual(second.status_code, 200)

        sessions = web_server._db_sleep_session_repository().get_recent_sessions("u1", limit=7)
        self.assertTrue(sessions)
        total = sum(max(0, int(getattr(row, "winddowns_completed", 0) or 0)) for row in sessions)
        self.assertEqual(total, 2)

        profile["web_device_commands"] = {"u1": []}

        dashboard = self.client.get("/v1/mobile/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        insight = dashboard.json().get("weekly_insight", {})
        self.assertEqual(int(insight.get("wind_down_sessions", 0)), 2)

        metrics_response = self.client.get("/v1/mobile/beta/metrics")
        self.assertEqual(metrics_response.status_code, 200)
        metrics = metrics_response.json().get("metrics", {})
        self.assertEqual(int(metrics.get("wind_down_sessions_7d", 0)), 2)

    @patch("web_server._save_profile")
    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    def test_command_metrics_are_db_first_for_beta_metrics(
        self,
        mock_require_user,
        mock_safe_profile,
        _mock_save,
    ):
        profile: dict = {}
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        create_response = self.client.post("/v1/mobile/device-commands", json={"action": "optimize_room"})
        self.assertEqual(create_response.status_code, 200)

        rows = profile.get("web_device_commands", {}).get("u1", [])
        self.assertTrue(rows)
        stale_iso = web_server.to_iso(web_server.utcnow() - timedelta(minutes=10))
        rows[0]["created_at"] = stale_iso
        rows[0]["updated_at"] = stale_iso
        rows[0]["status"] = "queued"

        sync_response = self.client.get("/v1/mobile/beta/metrics")
        self.assertEqual(sync_response.status_code, 200)

        profile["web_device_commands"] = {"u1": []}
        metrics_response = self.client.get("/v1/mobile/beta/metrics")
        self.assertEqual(metrics_response.status_code, 200)
        metrics = metrics_response.json().get("metrics", {})
        self.assertEqual(int(metrics.get("command_total_7d", 0)), 1)
        self.assertEqual(int(metrics.get("command_completion_rate_pct", 0)), 100)


if __name__ == "__main__":
    unittest.main()
