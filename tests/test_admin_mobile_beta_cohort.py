import os
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_server
from env_isolation import reset_auth_service_singleton


class TestAdminMobileBetaCohort(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self._db_path = Path(self._tmp.name) / "admin_beta_cohort.sqlite3"
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

    def _seed_user(
        self,
        *,
        email: str,
        full_name: str,
        command_total_7d: int,
        command_completion_rate_pct: int,
        wind_down_sessions_7d: int,
        activation_progress_pct: int,
        first_3_nights_complete: bool = True,
    ) -> str:
        now = datetime(2026, 3, 14, 0, 0, tzinfo=timezone.utc)
        user_repo = web_server._db_user_repository()
        beta_repo = web_server._db_beta_progress_repository()
        user = user_repo.create_user(
            email=email,
            password_hash="hashed_pw",
            full_name=full_name,
        )

        step_keys = ["signup"]
        if first_3_nights_complete:
            step_keys = [
                "signup",
                "first_scene_preview",
                "first_automation",
                "first_winddown",
                "timeline_review",
            ]
        beta_repo.sync_first_three_nights_steps(
            user_id=str(user.id),
            step_keys=step_keys,
            now_utc=now,
        )
        beta_repo.upsert_beta_metrics_snapshot(
            str(user.id),
            {
                "window_days": 7,
                "activation_progress_pct": activation_progress_pct,
                "first_3_nights_completed": 5 if first_3_nights_complete else 1,
                "first_3_nights_total": 5,
                "command_total_7d": command_total_7d,
                "command_completion_rate_pct": command_completion_rate_pct,
                "wind_down_sessions_7d": wind_down_sessions_7d,
                "nightly_feedback_total": 1 if command_total_7d > 0 else 0,
                "nightly_feedback_helpful_pct": 100 if command_total_7d > 0 else 0,
                "cohort_status_line": "beta progress",
                "quality_gate_line": "quality check",
                "generated_at_utc": web_server.to_iso(now),
            },
            now_utc=now,
        )
        return str(user.id)

    @patch("web_server._require_admin")
    def test_enroll_by_email_updates_cohort_report(self, mock_require_admin):
        mock_require_admin.return_value = {"user_id": "admin_1", "role": "owner"}
        user_id = self._seed_user(
            email="kw1@example.com",
            full_name="Kuwait Tester One",
            command_total_7d=2,
            command_completion_rate_pct=100,
            wind_down_sessions_7d=1,
            activation_progress_pct=92,
            first_3_nights_complete=True,
        )

        response = self.client.post(
            "/v1/admin/mobile/beta-cohort/enroll",
            json={
                "email": "kw1@example.com",
                "cohort_key": "kuwait_beta",
                "country_code": "KW",
                "status": "active",
                "notes": "Wave 1",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get("ok"))
        member = body.get("member", {})
        self.assertEqual(str(member.get("user_id", "")), user_id)
        self.assertEqual(str(member.get("cohort_key", "")), "kuwait_beta")
        self.assertEqual(str(member.get("country_code", "")), "KW")

        report = body.get("report", {})
        self.assertEqual(int(report.get("enrolled_testers", 0)), 1)
        self.assertEqual(int(report.get("active_testers_7d", 0)), 1)
        self.assertEqual(int(report.get("remaining_to_target_min", 0)), 9)

    @patch("web_server._require_admin")
    def test_report_hits_target_band_for_three_active_testers(self, mock_require_admin):
        mock_require_admin.return_value = {"user_id": "admin_1", "role": "owner"}
        users = [
            ("kw_a@example.com", "Tester A"),
            ("kw_b@example.com", "Tester B"),
            ("kw_c@example.com", "Tester C"),
        ]
        for email, name in users:
            self._seed_user(
                email=email,
                full_name=name,
                command_total_7d=3,
                command_completion_rate_pct=100,
                wind_down_sessions_7d=2,
                activation_progress_pct=95,
                first_3_nights_complete=True,
            )
            enroll = self.client.post(
                "/v1/admin/mobile/beta-cohort/enroll",
                json={
                    "email": email,
                    "cohort_key": "kuwait_beta",
                    "country_code": "KW",
                    "status": "active",
                },
            )
            self.assertEqual(enroll.status_code, 200)

        report_response = self.client.get(
            "/v1/admin/mobile/beta-cohort?cohort_key=kuwait_beta&target_min=3&target_max=5",
        )
        self.assertEqual(report_response.status_code, 200)
        report = report_response.json().get("report", {})
        self.assertEqual(int(report.get("enrolled_testers", 0)), 3)
        self.assertEqual(int(report.get("active_testers_7d", 0)), 3)
        self.assertTrue(bool(report.get("target_band_hit", False)))
        self.assertEqual(report.get("blockers", []), [])


if __name__ == "__main__":
    unittest.main()
