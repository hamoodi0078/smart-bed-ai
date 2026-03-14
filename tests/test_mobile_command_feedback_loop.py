import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_server


class TestMobileCommandFeedbackLoop(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmp.name) / "mobile_command_feedback.sqlite3"
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
    def test_feedback_updates_dashboard_and_beta_metrics(
        self,
        mock_require_user,
        mock_safe_profile,
        _mock_save,
    ):
        profile: dict = {}
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        created = self.client.post("/v1/mobile/device-commands", json={"action": "optimize_room"})
        self.assertEqual(created.status_code, 200)
        command_id = str(created.json().get("command_id", ""))
        self.assertTrue(command_id)

        helpful = self.client.post(
            f"/v1/mobile/device-commands/{command_id}/feedback",
            json={"vote": "helpful"},
        )
        self.assertEqual(helpful.status_code, 200)
        helpful_feedback = helpful.json().get("feedback", {})
        self.assertEqual(int(helpful_feedback.get("helpful_count", 0)), 1)
        self.assertEqual(int(helpful_feedback.get("total_votes", 0)), 1)
        self.assertEqual(int(helpful_feedback.get("helpful_pct", 0)), 100)

        duplicate = self.client.post(
            f"/v1/mobile/device-commands/{command_id}/feedback",
            json={"vote": "helpful"},
        )
        self.assertEqual(duplicate.status_code, 200)
        duplicate_feedback = duplicate.json().get("feedback", {})
        self.assertEqual(int(duplicate_feedback.get("helpful_count", 0)), 1)
        self.assertEqual(int(duplicate_feedback.get("total_votes", 0)), 1)

        switched = self.client.post(
            f"/v1/mobile/device-commands/{command_id}/feedback",
            json={"vote": "not_helpful", "note": "Still too noisy after trigger"},
        )
        self.assertEqual(switched.status_code, 200)
        switched_feedback = switched.json().get("feedback", {})
        self.assertEqual(int(switched_feedback.get("helpful_count", 0)), 0)
        self.assertEqual(int(switched_feedback.get("not_helpful_count", 0)), 1)
        self.assertEqual(int(switched_feedback.get("total_votes", 0)), 1)
        self.assertEqual(int(switched_feedback.get("helpful_pct", 0)), 0)
        self.assertEqual(str(switched_feedback.get("last_command_id", "")), command_id)

        dashboard = self.client.get("/v1/mobile/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        dashboard_feedback = dashboard.json().get("automation_feedback_loop", {})
        self.assertEqual(int(dashboard_feedback.get("total_votes", 0)), 1)
        self.assertEqual(int(dashboard_feedback.get("not_helpful_count", 0)), 1)
        self.assertEqual(str(dashboard_feedback.get("last_command_id", "")), command_id)

        beta_metrics = self.client.get("/v1/mobile/beta/metrics")
        self.assertEqual(beta_metrics.status_code, 200)
        metrics = beta_metrics.json().get("metrics", {})
        self.assertEqual(int(metrics.get("automation_feedback_total", 0)), 1)
        self.assertEqual(int(metrics.get("automation_feedback_helpful_pct", 0)), 0)

    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    def test_feedback_rejects_unknown_command(
        self,
        mock_require_user,
        mock_safe_profile,
    ):
        mock_safe_profile.return_value = {}
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        response = self.client.post(
            "/v1/mobile/device-commands/cmd_missing/feedback",
            json={"vote": "helpful"},
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
