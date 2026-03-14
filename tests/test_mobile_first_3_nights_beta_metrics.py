import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_server


class TestMobileFirst3NightsAndBetaMetrics(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmp.name) / "beta_progress.sqlite3"
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
    def test_dashboard_includes_checklist_and_feedback_payloads(
        self,
        mock_require_user,
        mock_safe_profile,
        _mock_save,
    ):
        profile: dict = {}
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        response = self.client.get("/v1/mobile/dashboard")
        self.assertEqual(response.status_code, 200)
        body = response.json()

        checklist = body.get("first_3_nights_checklist", {})
        self.assertEqual(int(checklist.get("total_steps", 0)), 5)
        self.assertGreaterEqual(int(checklist.get("completed_steps", 0)), 1)
        self.assertEqual(len(checklist.get("steps", [])), 5)

        feedback = body.get("nightly_summary_feedback", {})
        self.assertEqual(int(feedback.get("helpful_count", 0)), 0)
        self.assertEqual(int(feedback.get("not_helpful_count", 0)), 0)

        stored = web_server._db_beta_progress_repository().get_first_three_nights_state("u1")
        self.assertTrue(str(stored.get("signup_completed_at_utc", "")).strip())

    @patch("web_server._save_profile")
    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    def test_checklist_auto_progress_and_timeline_review_completion(
        self,
        mock_require_user,
        mock_safe_profile,
        _mock_save,
    ):
        profile = {
            "web_scene_preview": {
                "u1": {
                    "scene_key": "calm_recovery",
                    "active": False,
                }
            },
            "web_device_commands": {
                "u1": [
                    {
                        "id": "cmd1",
                        "action": "winddown",
                        "status": "completed",
                        "created_at": "2026-03-13T21:00:00+00:00",
                        "updated_at": "2026-03-13T21:05:00+00:00",
                        "completed_at": "2026-03-13T21:05:00+00:00",
                    }
                ]
            },
            "sleep": {"wind_down_started_at_utc": "2026-03-13T21:00:00+00:00"},
        }
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        initial = self.client.get("/v1/mobile/first-3-nights")
        self.assertEqual(initial.status_code, 200)
        initial_checklist = initial.json().get("checklist", {})
        self.assertEqual(int(initial_checklist.get("completed_steps", 0)), 4)
        self.assertEqual(str(initial_checklist.get("next_step_key", "")), "timeline_review")

        completed = self.client.post(
            "/v1/mobile/first-3-nights/complete",
            json={"step_key": "timeline_review"},
        )
        self.assertEqual(completed.status_code, 200)
        final_checklist = completed.json().get("checklist", {})
        self.assertTrue(bool(final_checklist.get("is_complete", False)))
        self.assertEqual(int(final_checklist.get("completed_steps", 0)), 5)

    @patch("web_server._save_profile")
    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    def test_feedback_endpoint_and_beta_metrics_reflect_votes(
        self,
        mock_require_user,
        mock_safe_profile,
        _mock_save,
    ):
        profile = {
            "web_device_commands": {
                "u1": [
                    {
                        "id": "cmd1",
                        "action": "winddown",
                        "status": "completed",
                        "created_at": "2026-03-12T21:00:00+00:00",
                        "updated_at": "2026-03-12T21:05:00+00:00",
                        "completed_at": "2026-03-12T21:05:00+00:00",
                    }
                ]
            }
        }
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        helpful = self.client.post(
            "/v1/mobile/nightly-summary/feedback",
            json={
                "vote": "helpful",
                "summary_generated_at_utc": "2026-03-13T22:00:00+00:00",
            },
        )
        self.assertEqual(helpful.status_code, 200)
        self.assertEqual(int(helpful.json().get("feedback", {}).get("helpful_count", 0)), 1)

        duplicate = self.client.post(
            "/v1/mobile/nightly-summary/feedback",
            json={
                "vote": "helpful",
                "summary_generated_at_utc": "2026-03-13T22:00:00+00:00",
            },
        )
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(int(duplicate.json().get("feedback", {}).get("helpful_count", 0)), 1)

        not_helpful = self.client.post(
            "/v1/mobile/nightly-summary/feedback",
            json={
                "vote": "not_helpful",
                "summary_generated_at_utc": "2026-03-14T22:00:00+00:00",
            },
        )
        self.assertEqual(not_helpful.status_code, 200)
        self.assertEqual(int(not_helpful.json().get("feedback", {}).get("not_helpful_count", 0)), 1)

        metrics_response = self.client.get("/v1/mobile/beta/metrics")
        self.assertEqual(metrics_response.status_code, 200)
        metrics = metrics_response.json().get("metrics", {})
        self.assertEqual(int(metrics.get("nightly_feedback_total", 0)), 2)
        self.assertEqual(int(metrics.get("nightly_feedback_helpful_pct", 0)), 50)
        self.assertIn("automation_feedback_total", metrics)
        self.assertIn("automation_feedback_helpful_pct", metrics)
        self.assertIn("activation_progress_pct", metrics)
        snapshot = web_server._db_beta_progress_repository().get_beta_metrics_snapshot("u1")
        self.assertEqual(int(snapshot.get("nightly_feedback_total", 0)), 2)


if __name__ == "__main__":
    unittest.main()
