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
    def test_dashboard_pauses_weekly_insight_when_disabled(
        self,
        mock_require_user,
        mock_safe_profile,
        _mock_save,
    ):
        profile = {
            "web_settings": {
                "u1": {
                    "weekly_insight_enabled": False,
                }
            }
        }
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        client = TestClient(web_server.app)
        response = client.get("/v1/mobile/dashboard")
        self.assertEqual(response.status_code, 200)
        weekly = response.json().get("weekly_insight", {})
        self.assertEqual(str(weekly.get("trend", "")), "paused")
        self.assertIn("paused", str(weekly.get("headline", "")).lower())

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

    @patch("web_server._save_profile")
    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    @patch("web_server._quiet_hours_status_timeline_item", return_value=None)
    @patch("web_server._automation_cooldown_timeline_items", return_value=[])
    @patch("web_server.utcnow")
    def test_timeline_skips_bedtime_drift_row_when_automation_disabled(
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
            },
            "web_settings": {
                "u1": {
                    "bedtime_drift_automation_enabled": False,
                }
            },
        }
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        client = TestClient(web_server.app)
        response = client.get("/v1/mobile/timeline")
        self.assertEqual(response.status_code, 200)
        rows = response.json().get("items", [])
        self.assertFalse(
            any(
                str(row.get("event", "")).startswith("Predictive alert:")
                for row in rows
                if isinstance(row, dict)
            )
        )
        self.assertFalse(
            bool(str(profile.get("sleep", {}).get("last_bedtime_drift_alert_date", "")).strip())
        )

    @patch("web_server._save_profile")
    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    @patch("web_server.utcnow")
    def test_quiet_hours_override_uses_user_setting_limit_minutes(
        self,
        mock_utcnow,
        mock_require_user,
        mock_safe_profile,
        _mock_save,
    ):
        now = datetime(2026, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
        mock_utcnow.return_value = now
        profile = {
            "web_settings": {
                "u1": {
                    "quiet_hours_override_limit_minutes": 30,
                }
            }
        }
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        client = TestClient(web_server.app)
        response = client.post("/v1/mobile/device-commands", json={"action": "quiet_hours_override"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        override_until = web_server.from_iso(str(body.get("override_until_utc", "")))
        delta_minutes = int((web_server.ensure_utc(override_until) - now).total_seconds() / 60.0)
        self.assertLessEqual(delta_minutes, 30)
        self.assertGreaterEqual(delta_minutes, 29)


if __name__ == "__main__":
    unittest.main()
