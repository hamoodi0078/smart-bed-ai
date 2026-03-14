import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_server


class TestMobileTimelinePrioritization(unittest.TestCase):
    @patch("web_server._save_profile")
    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    def test_timeline_endpoint_sorts_cards_by_priority(
        self,
        mock_require_user,
        mock_safe_profile,
        _mock_save,
    ):
        profile = {
            "web_timeline": {
                "u1": [
                    {"time": "Anytime", "event": "Floating AI chat control", "status": "available"},
                    {"time": "22:30", "event": "Bedtime routine scheduled", "status": "ready"},
                    {"time": "Now", "event": "Wind-down routine armed", "status": "active"},
                    {"time": "Now", "event": "Wake recovery queued", "status": "queued"},
                    {"time": "Now", "event": "Quiet hours override enabled", "status": "override"},
                ]
            }
        }
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        with (
            patch(
                "web_server._mobile_timeline_items_db_first",
                side_effect=lambda user_id, profile_items, trace_id="", limit=20: web_server._normalize_timeline_items(
                    profile_items
                ),
            ),
            patch("web_server._progress_user_commands", return_value=([], False)),
            patch("web_server._quiet_hours_status_timeline_item", return_value=None),
            patch("web_server._automation_cooldown_timeline_items", return_value=[]),
            patch("web_server._bedtime_drift_timeline_item", return_value=(None, False)),
        ):
            client = TestClient(web_server.app)
            response = client.get("/v1/mobile/timeline")

        self.assertEqual(response.status_code, 200)
        items = response.json().get("items", [])
        self.assertTrue(bool(items))

        priorities = [int((row if isinstance(row, dict) else {}).get("priority", 0) or 0) for row in items]
        self.assertEqual(priorities, sorted(priorities, reverse=True))
        self.assertEqual(str(items[0].get("status", "")), "override")
        self.assertTrue(all("priority" in row for row in items if isinstance(row, dict)))


if __name__ == "__main__":
    unittest.main()
