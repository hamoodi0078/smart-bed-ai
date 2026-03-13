import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_server


class TestMobileBedtimeDriftSummary(unittest.TestCase):
    @patch("web_server._save_profile")
    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    def test_dashboard_includes_nightly_summary_and_drift_field(
        self,
        mock_require_user,
        mock_safe_profile,
        _mock_save,
    ):
        profile = {
            "sleep": {
                "bedtime_history": [
                    "2026-03-01T22:00:00",
                    "2026-03-02T23:10:00",
                    "2026-03-03T00:20:00",
                    "2026-03-04T01:35:00",
                    "2026-03-05T02:45:00",
                ],
            }
        }
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        client = TestClient(web_server.app)
        response = client.get("/v1/mobile/dashboard")
        self.assertEqual(response.status_code, 200)
        body = response.json()

        nightly = body.get("nightly_summary", {})
        self.assertTrue(str(nightly.get("headline", "")).strip())
        self.assertTrue(str(nightly.get("sleep_quality_line", "")).strip())
        self.assertTrue(str(nightly.get("consistency_line", "")).strip())
        self.assertTrue(str(nightly.get("recovery_plan_line", "")).strip())
        self.assertIn("bedtime_drift_alert", body)

    @patch("web_server._save_profile")
    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    @patch("web_server._quiet_hours_status_timeline_item", return_value=None)
    @patch("web_server._automation_cooldown_timeline_items", return_value=[])
    @patch("web_server.utcnow")
    def test_timeline_includes_predictive_bedtime_drift_row(
        self,
        mock_utcnow,
        _mock_cooldown,
        _mock_quiet,
        mock_require_user,
        mock_safe_profile,
        _mock_save,
    ):
        now = datetime(2026, 3, 6, 20, 0, 0, tzinfo=timezone.utc)
        mock_utcnow.return_value = now
        profile = {
            "sleep": {
                "bedtime_history": [
                    "2026-03-01T22:00:00",
                    "2026-03-02T23:15:00",
                    "2026-03-03T00:30:00",
                    "2026-03-04T01:40:00",
                    "2026-03-05T02:50:00",
                ],
            }
        }
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        client = TestClient(web_server.app)
        response = client.get("/v1/mobile/timeline")
        self.assertEqual(response.status_code, 200)
        rows = response.json().get("items", [])
        self.assertTrue(
            any(
                str(row.get("event", "")).startswith("Predictive alert:")
                for row in rows
                if isinstance(row, dict)
            )
        )
        self.assertEqual(
            str(profile.get("sleep", {}).get("last_bedtime_drift_alert_date", "")),
            "2026-03-06",
        )


if __name__ == "__main__":
    unittest.main()
