import os
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_server
from env_isolation import reset_auth_service_singleton


class TestAdminMobileBetaAcceptance(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self._db_path = Path(self._tmp.name) / "admin_beta_acceptance.sqlite3"
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

    def _seed_tester(
        self,
        *,
        email: str,
        full_name: str,
        completed: bool,
        command_completion_rate_pct: int,
        wind_down_sessions_7d: int,
        activation_progress_pct: int,
        generated_at_utc: datetime,
    ) -> None:
        user_repo = web_server._db_user_repository()
        beta_repo = web_server._db_beta_progress_repository()
        user = user_repo.create_user(
            email=email,
            password_hash="hashed_pw",
            full_name=full_name,
        )
        if completed:
            step_keys = [
                "signup",
                "first_scene_preview",
                "first_automation",
                "first_winddown",
                "timeline_review",
            ]
        else:
            step_keys = ["signup", "first_scene_preview"]
        beta_repo.sync_first_three_nights_steps(
            user_id=str(user.id),
            step_keys=step_keys,
            now_utc=generated_at_utc,
        )
        beta_repo.upsert_beta_metrics_snapshot(
            str(user.id),
            {
                "window_days": 7,
                "activation_progress_pct": activation_progress_pct,
                "first_3_nights_completed": 5 if completed else 2,
                "first_3_nights_total": 5,
                "command_total_7d": 3,
                "command_completion_rate_pct": command_completion_rate_pct,
                "wind_down_sessions_7d": wind_down_sessions_7d,
                "nightly_feedback_total": 1,
                "nightly_feedback_helpful_pct": 100,
                "cohort_status_line": "beta progress",
                "quality_gate_line": "quality check",
                "generated_at_utc": web_server.to_iso(generated_at_utc),
            },
            now_utc=generated_at_utc,
        )

    @patch("web_server._require_admin")
    def test_default_scope_reports_blocker_when_scripted_quality_is_below_target(
        self,
        mock_require_admin,
    ):
        mock_require_admin.return_value = {"user_id": "admin_1", "role": "owner"}
        base_time = datetime(2026, 3, 14, 0, 0, tzinfo=timezone.utc)

        self._seed_tester(
            email="good1@example.com",
            full_name="Good One",
            completed=True,
            command_completion_rate_pct=100,
            wind_down_sessions_7d=2,
            activation_progress_pct=95,
            generated_at_utc=base_time,
        )
        self._seed_tester(
            email="good2@example.com",
            full_name="Good Two",
            completed=True,
            command_completion_rate_pct=100,
            wind_down_sessions_7d=2,
            activation_progress_pct=96,
            generated_at_utc=base_time,
        )
        self._seed_tester(
            email="good3@example.com",
            full_name="Good Three",
            completed=True,
            command_completion_rate_pct=90,
            wind_down_sessions_7d=1,
            activation_progress_pct=94,
            generated_at_utc=base_time,
        )
        self._seed_tester(
            email="weak@example.com",
            full_name="Weak User",
            completed=False,
            command_completion_rate_pct=40,
            wind_down_sessions_7d=0,
            activation_progress_pct=25,
            generated_at_utc=base_time,
        )

        response = self.client.get("/v1/admin/mobile/beta-acceptance")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get("ok"))
        report = body.get("report", {})

        self.assertEqual(int(report.get("testers_in_scope", 0)), 4)
        self.assertEqual(int(report.get("milestone_complete_testers", 0)), 3)
        self.assertEqual(int(report.get("scripted_flow_success_testers", 0)), 3)
        self.assertEqual(int(report.get("scripted_flow_success_pct", 0)), 75)
        self.assertFalse(bool(report.get("exit_gate_pass", True)))
        blockers = " ".join(report.get("blockers", []))
        self.assertIn("Scripted flow success", blockers)

    @patch("web_server._require_admin")
    def test_three_tester_scope_passes_exit_gate_when_all_three_are_strong(
        self,
        mock_require_admin,
    ):
        mock_require_admin.return_value = {"user_id": "admin_1", "role": "owner"}
        base_time = datetime(2026, 3, 14, 0, 0, tzinfo=timezone.utc)

        self._seed_tester(
            email="good1@example.com",
            full_name="Good One",
            completed=True,
            command_completion_rate_pct=100,
            wind_down_sessions_7d=2,
            activation_progress_pct=95,
            generated_at_utc=base_time,
        )
        self._seed_tester(
            email="good2@example.com",
            full_name="Good Two",
            completed=True,
            command_completion_rate_pct=100,
            wind_down_sessions_7d=2,
            activation_progress_pct=96,
            generated_at_utc=base_time,
        )
        self._seed_tester(
            email="good3@example.com",
            full_name="Good Three",
            completed=True,
            command_completion_rate_pct=90,
            wind_down_sessions_7d=1,
            activation_progress_pct=94,
            generated_at_utc=base_time,
        )
        self._seed_tester(
            email="weak@example.com",
            full_name="Weak User",
            completed=False,
            command_completion_rate_pct=40,
            wind_down_sessions_7d=0,
            activation_progress_pct=25,
            generated_at_utc=base_time,
        )

        response = self.client.get("/v1/admin/mobile/beta-acceptance?max_testers=3&min_required=3")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get("ok"))
        report = body.get("report", {})

        self.assertEqual(int(report.get("testers_in_scope", 0)), 3)
        self.assertEqual(int(report.get("scripted_flow_success_pct", 0)), 100)
        self.assertEqual(int(report.get("exit_gate_ready_testers", 0)), 3)
        self.assertTrue(bool(report.get("exit_gate_pass", False)))
        self.assertEqual(report.get("blockers", []), [])


if __name__ == "__main__":
    unittest.main()
