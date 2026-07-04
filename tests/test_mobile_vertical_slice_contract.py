import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from Storage.subscription_store import SubscriptionStore
import web_server
from env_isolation import reset_auth_service_singleton


def _legacy_sha256(password: str) -> str:
    return hashlib.sha256((password or "").encode("utf-8")).hexdigest()


class TestMobileVerticalSliceContract(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self._subscription_db_path = Path(self._tmp.name) / "subscription_db.json"
        self._profile_path = Path(self._tmp.name) / "user_profile.json"
        self._sqlite_path = Path(self._tmp.name) / "mobile_vertical_slice.sqlite3"
        self._database_url = f"sqlite:///{self._sqlite_path.as_posix()}"

        self.store = SubscriptionStore(db_path=self._subscription_db_path)
        self.store.hash_password = lambda password: _legacy_sha256(password)
        self.store.check_password = (
            lambda password, stored_hash: stored_hash == _legacy_sha256(password)
        )

        self._env_patch = patch.dict(
            os.environ,
            {"DATABASE_URL": self._database_url},
            clear=False,
        )
        self._patch_store = patch.object(web_server, "store", self.store)
        self._patch_profile = patch.object(
            web_server, "PROFILE_PATH", self._profile_path
        )

        self._env_patch.start()
        self._patch_store.start()
        self._patch_profile.start()

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

        self._patch_profile.stop()
        self._patch_store.stop()
        self._env_patch.stop()
        reset_auth_service_singleton()
        self._tmp.cleanup()

    def test_signup_dashboard_quick_action_scene_preview_timeline_contract(self):
        register = self.client.post(
            "/v1/mobile/auth/register",
            json={
                "email": "vertical@example.com",
                "password": "Secret1234",
                "name": "Vertical User",
                "client_name": "flutter_contract",
            },
        )
        self.assertEqual(register.status_code, 200)
        register_body = register.json()
        self.assertTrue(register_body.get("ok"))
        access_token = str(register_body.get("access_token", ""))
        self.assertTrue(access_token)

        headers = {"Authorization": f"Bearer {access_token}"}

        dashboard = self.client.get("/v1/mobile/dashboard", headers=headers)
        self.assertEqual(dashboard.status_code, 200)
        dashboard_body = dashboard.json()
        self.assertIn("name", dashboard_body)
        self.assertIn("weekly_insight", dashboard_body)
        self.assertIn("nightly_summary", dashboard_body)
        self.assertIn("automation_feedback_loop", dashboard_body)

        quick_action = self.client.post(
            "/v1/mobile/device-commands",
            json={"action": "winddown"},
            headers=headers,
        )
        self.assertEqual(quick_action.status_code, 200)
        quick_action_body = quick_action.json()
        self.assertTrue(quick_action_body.get("ok"))
        self.assertEqual(quick_action_body.get("action"), "winddown")
        command_id = str(quick_action_body.get("command_id", ""))
        self.assertTrue(command_id)

        preview = self.client.post(
            "/v1/mobile/scenes/preview",
            json={"scene_key": "calm_recovery"},
            headers=headers,
        )
        self.assertEqual(preview.status_code, 200)
        preview_body = preview.json()
        self.assertTrue(preview_body.get("ok"))
        self.assertEqual(preview_body.get("scene_key"), "calm_recovery")
        self.assertTrue(bool(preview_body.get("premium_quota_exempt")))

        timeline = self.client.get("/v1/mobile/timeline", headers=headers)
        self.assertEqual(timeline.status_code, 200)
        timeline_body = timeline.json()
        self.assertTrue(timeline_body.get("ok"))
        items = timeline_body.get("items", [])
        self.assertTrue(isinstance(items, list))
        self.assertTrue(
            any(
                isinstance(row, dict)
                and str(row.get("command_id", "") or "") == command_id
                for row in items
            )
        )


if __name__ == "__main__":
    unittest.main()
