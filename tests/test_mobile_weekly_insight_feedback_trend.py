import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_server


class TestMobileWeeklyInsightFeedbackTrend(unittest.TestCase):
    @patch("web_server._save_profile")
    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    def test_dashboard_weekly_insight_attention_when_feedback_is_low(
        self,
        mock_require_user,
        mock_safe_profile,
        _mock_save,
    ):
        profile: dict = {}
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        commands = [
            {"id": "cmd_1", "action": "winddown", "status": "completed"},
            {"id": "cmd_2", "action": "wake_recovery", "status": "completed"},
            {"id": "cmd_3", "action": "optimize_room", "status": "completed"},
        ]

        with (
            patch("web_server._progress_user_commands", return_value=(commands, False)),
            patch(
                "web_server._nightly_summary_feedback_for_user",
                return_value={
                    "helpful_count": 1,
                    "not_helpful_count": 3,
                    "last_vote": "not_helpful",
                    "last_vote_at_utc": "2026-03-14T00:00:00Z",
                    "last_summary_generated_at_utc": "",
                },
            ),
            patch(
                "web_server._command_feedback_for_user",
                return_value={
                    "helpful_count": 0,
                    "not_helpful_count": 2,
                    "last_vote": "not_helpful",
                    "last_vote_at_utc": "2026-03-14T00:00:00Z",
                    "last_command_id": "cmd_3",
                    "last_command_action": "optimize_room",
                },
            ),
        ):
            client = TestClient(web_server.app)
            response = client.get("/v1/mobile/dashboard")

        self.assertEqual(response.status_code, 200)
        insight = response.json().get("weekly_insight", {})
        self.assertEqual(str(insight.get("trend", "")), "attention")
        self.assertIn("feedback trend", str(insight.get("headline", "")).lower())
        self.assertIn("% helpful feedback", str(insight.get("summary", "")).lower())

    @patch("web_server._save_profile")
    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    def test_dashboard_weekly_insight_up_when_feedback_is_strong(
        self,
        mock_require_user,
        mock_safe_profile,
        _mock_save,
    ):
        profile: dict = {}
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        commands = [
            {"id": "cmd_1", "action": "winddown", "status": "completed"},
            {"id": "cmd_2", "action": "winddown", "status": "completed"},
            {"id": "cmd_3", "action": "optimize_room", "status": "completed"},
            {"id": "cmd_4", "action": "reactive_lights", "status": "completed"},
        ]

        with (
            patch("web_server._progress_user_commands", return_value=(commands, False)),
            patch(
                "web_server._nightly_summary_feedback_for_user",
                return_value={
                    "helpful_count": 4,
                    "not_helpful_count": 0,
                    "last_vote": "helpful",
                    "last_vote_at_utc": "2026-03-14T00:00:00Z",
                    "last_summary_generated_at_utc": "",
                },
            ),
            patch(
                "web_server._command_feedback_for_user",
                return_value={
                    "helpful_count": 2,
                    "not_helpful_count": 0,
                    "last_vote": "helpful",
                    "last_vote_at_utc": "2026-03-14T00:00:00Z",
                    "last_command_id": "cmd_4",
                    "last_command_action": "reactive_lights",
                },
            ),
        ):
            client = TestClient(web_server.app)
            response = client.get("/v1/mobile/dashboard")

        self.assertEqual(response.status_code, 200)
        insight = response.json().get("weekly_insight", {})
        self.assertEqual(str(insight.get("trend", "")), "up")
        self.assertIn("feedback trend", str(insight.get("headline", "")).lower())
        self.assertIn("% helpful feedback", str(insight.get("summary", "")).lower())


if __name__ == "__main__":
    unittest.main()
