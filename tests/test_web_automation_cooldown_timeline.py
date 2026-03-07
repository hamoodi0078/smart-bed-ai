import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_server


class TestAutomationCooldownTimeline(unittest.TestCase):
    @patch("web_server.build_default_automations", return_value=[])
    @patch("web_server.AutomationRegistry")
    def test_cooldown_rows_show_next_run_minutes(self, mock_registry, _mock_defaults):
        registry_instance = mock_registry.return_value
        registry_instance.cooldown_status.return_value = [
            {"name": "sleep_time_suggestion", "next_run_in_minutes": 18},
            {"name": "fajr_gentle_light", "next_run_in_minutes": 0},
        ]

        rows = web_server._automation_cooldown_timeline_items()

        self.assertEqual(len(rows), 2)
        self.assertIn("next run available in 18 min", rows[0].get("event", ""))
        self.assertEqual(rows[0].get("status"), "cooldown")
        self.assertIn("available now", rows[1].get("event", ""))
        self.assertEqual(rows[1].get("status"), "ready")

    @patch(
        "web_server._automation_cooldown_timeline_items",
        return_value=[
            {
                "time": "in 12 min",
                "event": "sleep time suggestion: next run available in 12 min",
                "status": "cooldown",
            }
        ],
    )
    @patch(
        "web_server._quiet_hours_status_timeline_item",
        return_value={
            "time": "Now",
            "event": "Quiet hours active (22:00-07:00). Non-critical automations are paused.",
            "status": "quiet",
        },
    )
    @patch("web_server._safe_profile", return_value={})
    @patch("web_server._require_user", return_value={"user_id": "u1", "email": "u1@example.com"})
    def test_mobile_timeline_includes_quiet_status_and_cooldown_display(
        self,
        _mock_user,
        _mock_profile,
        _mock_quiet_row,
        _mock_cooldowns,
    ):
        client = TestClient(web_server.app)
        response = client.get("/v1/mobile/timeline")
        self.assertEqual(response.status_code, 200)

        body = response.json()
        items = body.get("items", [])
        self.assertTrue(items)
        self.assertIn("quiet hours active", str(items[0].get("event", "")).lower())
        self.assertIn("next run available in 12 min", str(items[1].get("event", "")).lower())

    @patch("web_server._compute_quiet_hours_override_until_utc", return_value="2026-03-06T07:00:00+00:00")
    @patch("web_server._save_profile")
    @patch("web_server._safe_profile", return_value={})
    @patch("web_server._require_user", return_value={"user_id": "u1", "email": "u1@example.com"})
    def test_quiet_override_command_sets_override_until(
        self,
        _mock_user,
        _mock_profile,
        mock_save_profile,
        _mock_compute,
    ):
        client = TestClient(web_server.app)
        response = client.post("/v1/mobile/device-commands", json={"action": "quiet_hours_override"})
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("action"), "quiet_hours_override")
        self.assertEqual(body.get("override_until_utc"), "2026-03-06T07:00:00+00:00")

        saved_profile = mock_save_profile.call_args[0][0]
        prefs = saved_profile.get("preferences", {})
        self.assertEqual(prefs.get("quiet_hours_override_until_utc"), "2026-03-06T07:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
