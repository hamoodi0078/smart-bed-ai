import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from Storage.subscription_store import SubscriptionStore
import web_server


def _legacy_sha256(password: str) -> str:
    return hashlib.sha256((password or "").encode("utf-8")).hexdigest()


class TestMobileMonetizationUndoApi(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._subscription_db_path = Path(self._tmp.name) / "subscription_db.json"
        self._profile_path = Path(self._tmp.name) / "user_profile.json"
        self._sqlite_path = Path(self._tmp.name) / "mobile_monetization.sqlite3"
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
        self._patch_profile = patch.object(web_server, "PROFILE_PATH", self._profile_path)

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
        self._tmp.cleanup()

    def _register(self, email: str) -> tuple[dict, dict[str, str]]:
        response = self.client.post(
            "/v1/mobile/auth/register",
            json={
                "email": email,
                "password": "secret123",
                "name": "Mobile User",
                "client_name": "flutter_contract",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        access_token = str(body.get("access_token", "") or "")
        self.assertTrue(access_token)
        headers = {"Authorization": f"Bearer {access_token}"}
        return body, headers

    def test_free_user_cannot_save_premium_scene(self):
        _, headers = self._register("free-scene@example.com")

        response = self.client.post(
            "/v1/mobile/scenes/save-tonight",
            json={"scene_key": "focus_momentum"},
            headers=headers,
        )
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertFalse(body.get("ok"))
        error = body.get("error", {})
        self.assertEqual(str(error.get("code", "")), "UNAUTHORIZED")
        self.assertIn("premium", str(error.get("message", "")).lower())

    def test_trial_user_can_save_premium_scene(self):
        register_body, headers = self._register("trial-scene@example.com")
        user_id = str(register_body.get("user", {}).get("user_id", "") or "")
        self.assertTrue(user_id)

        start_trial = self.client.post(
            "/v1/subscriptions/trial/start",
            json={"user_id": user_id},
            headers=headers,
        )
        self.assertEqual(start_trial.status_code, 200)

        response = self.client.post(
            "/v1/mobile/scenes/save-tonight",
            json={"scene_key": "focus_momentum"},
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get("ok"))
        self.assertTrue(bool(body.get("premium")))
        self.assertTrue(bool(body.get("saved_for_tonight")))

    def test_mobile_undo_reverts_last_command_timeline_item(self):
        _, headers = self._register("undo-mobile@example.com")

        command_response = self.client.post(
            "/v1/mobile/device-commands",
            json={"action": "optimize_room"},
            headers=headers,
        )
        self.assertEqual(command_response.status_code, 200)
        command_body = command_response.json()
        command_id = str(command_body.get("command_id", "") or "")
        self.assertTrue(command_id)

        status_before = self.client.get("/v1/mobile/actions/undo/status", headers=headers)
        self.assertEqual(status_before.status_code, 200)
        status_before_body = status_before.json()
        self.assertTrue(bool(status_before_body.get("can_undo")))
        self.assertEqual(str(status_before_body.get("action_type", "")), "device_command")

        undo_response = self.client.post("/v1/mobile/actions/undo", headers=headers, json={})
        self.assertEqual(undo_response.status_code, 200)
        undo_body = undo_response.json()
        self.assertTrue(undo_body.get("ok"))
        self.assertEqual(str(undo_body.get("undone", "")), "device_command")

        status_after = self.client.get("/v1/mobile/actions/undo/status", headers=headers)
        self.assertEqual(status_after.status_code, 200)
        self.assertFalse(bool(status_after.json().get("can_undo")))

        timeline = self.client.get("/v1/mobile/timeline", headers=headers)
        self.assertEqual(timeline.status_code, 200)
        rows = timeline.json().get("items", [])
        self.assertFalse(
            any(
                isinstance(row, dict)
                and str(row.get("command_id", "") or "") == command_id
                for row in rows
            )
        )

    def test_mobile_undo_without_action_returns_contract_error(self):
        _, headers = self._register("undo-empty@example.com")
        response = self.client.post("/v1/mobile/actions/undo", headers=headers, json={})
        self.assertEqual(response.status_code, 404)
        body = response.json()
        self.assertFalse(body.get("ok"))
        error = body.get("error", {})
        self.assertEqual(str(error.get("code", "")), "NOTHING_TO_UNDO")


if __name__ == "__main__":
    unittest.main()
