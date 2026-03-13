import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_server


class TestMobileWindDownWeeklyInsight(unittest.TestCase):
    @patch("web_server._save_profile")
    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    def test_dashboard_includes_weekly_insight_payload(
        self,
        mock_require_user,
        mock_safe_profile,
        _mock_save,
    ):
        profile: dict = {}
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        client = TestClient(web_server.app)
        response = client.get("/v1/mobile/dashboard")
        self.assertEqual(response.status_code, 200)
        body = response.json()

        insight = body.get("weekly_insight", {})
        self.assertEqual(int(insight.get("window_days", 0)), 7)
        self.assertIn(str(insight.get("trend", "")), {"up", "steady", "attention"})
        self.assertIn("headline", insight)
        self.assertIn("summary", insight)

    @patch("web_server._save_profile")
    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    def test_winddown_command_arms_sleep_state_and_controls(
        self,
        mock_require_user,
        mock_safe_profile,
        _mock_save,
    ):
        profile: dict = {}
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        client = TestClient(web_server.app)
        response = client.post("/v1/mobile/device-commands", json={"action": "winddown"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("minute", str(body.get("message", "")).lower())

        sleep = profile.get("sleep", {})
        self.assertTrue(bool(sleep.get("wind_down_enabled", False)))
        self.assertTrue(str(sleep.get("wind_down_started_at_utc", "")).strip())
        self.assertTrue(str(sleep.get("wind_down_target_end_utc", "")).strip())

        controls = profile.get("web_device_controls", {}).get("u1", {})
        self.assertTrue(bool(controls.get("lights_on", False)))
        self.assertTrue(bool(controls.get("audio_on", False)))

        timeline = profile.get("web_timeline", {}).get("u1", [])
        self.assertTrue(
            any(
                "wind-down routine armed" in str(row.get("event", "")).lower()
                for row in timeline
                if isinstance(row, dict)
            )
        )


if __name__ == "__main__":
    unittest.main()
