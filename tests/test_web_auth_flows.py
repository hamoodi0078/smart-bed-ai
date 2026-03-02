import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from Storage.subscription_store import SubscriptionStore
import web_server


def _legacy_sha256(password: str) -> str:
    return hashlib.sha256((password or "").encode("utf-8")).hexdigest()


class TestWebAuthFlows(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "subscription_db.json"
        self.profile_path = Path(self._tmp.name) / "user_profile.json"
        self.store = SubscriptionStore(db_path=self.db_path)

        # Keep auth tests independent from optional bcrypt installation state.
        self.store.hash_password = lambda password: _legacy_sha256(password)
        self.store.check_password = lambda password, stored_hash: stored_hash == _legacy_sha256(password)

        self._patch_store = patch.object(web_server, "store", self.store)
        self._patch_profile = patch.object(web_server, "PROFILE_PATH", self.profile_path)
        self._patch_store.start()
        self._patch_profile.start()
        self.client = TestClient(web_server.app)

    def tearDown(self):
        self._patch_profile.stop()
        self._patch_store.stop()
        self._tmp.cleanup()

    def _register(self, email: str = "user@example.com", password: str = "secret123", name: str = "User"):
        return self.client.post(
            "/v1/auth/register",
            json={"email": email, "password": password, "name": name},
        )

    def _login(self, email: str = "user@example.com", password: str = "secret123"):
        return self.client.post(
            "/v1/auth/login",
            json={"email": email, "password": password},
        )

    def test_register_creates_user_and_session(self):
        response = self._register()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("user", {}).get("email"), "user@example.com")

        token = self.client.cookies.get("sb_user_token")
        self.assertTrue(token)
        self.assertIn(token, self.store.db.get("user_sessions", {}))

    def test_login_returns_authenticated_user(self):
        self._register(email="login@example.com", password="letmein1")
        self.client.post("/v1/auth/logout")

        response = self._login(email="login@example.com", password="letmein1")
        self.assertEqual(response.status_code, 200)
        me = self.client.get("/v1/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json().get("user", {}).get("email"), "login@example.com")

    def test_admin_bootstrap_does_not_auto_promote_owner(self):
        register = self._register(email="admin-bootstrap@example.com", password="letmein1")
        user_id = register.json().get("user", {}).get("user_id")

        response = self.client.post(
            "/v1/admin/auth/login",
            json={"email": "admin-bootstrap@example.com", "password": "letmein1"},
        )
        self.assertEqual(response.status_code, 403)

        admin_row = self.store.get_admin_user(user_id)
        self.assertIsNotNone(admin_row)
        self.assertEqual(admin_row.get("role"), "viewer")

    def test_logout_revokes_server_session(self):
        self._register(email="logout@example.com", password="letmein1")
        token = self.client.cookies.get("sb_user_token")
        self.assertIn(token, self.store.db.get("user_sessions", {}))

        response = self.client.post("/v1/auth/logout")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(token, self.store.db.get("user_sessions", {}))

        me = self.client.get("/v1/auth/me")
        self.assertEqual(me.status_code, 401)

    def test_delete_data_removes_user_profile_and_sessions(self):
        register = self._register(email="delete@example.com", password="letmein1")
        body = register.json()
        user = body.get("user", {})
        user_id = user.get("user_id", "")
        user_email = user.get("email", "")

        settings = self.client.post("/v1/mobile/settings", json={})
        self.assertEqual(settings.status_code, 200)
        self.assertTrue(self.profile_path.exists())

        profile_before = json.loads(self.profile_path.read_text(encoding="utf-8"))
        self.assertIn(user_id, profile_before.get("web_settings", {}))

        delete_resp = self.client.post("/v1/auth/delete-data")
        self.assertEqual(delete_resp.status_code, 200)

        self.assertIsNone(self.store.get_user(user_id))
        self.assertIsNone(self.store.get_admin_user(user_id))
        self.assertFalse(any(s.get("user_id") == user_id for s in self.store.db.get("user_sessions", {}).values()))
        self.assertFalse(any(s.get("user_id") == user_id for s in self.store.db.get("admin_sessions", {}).values()))

        profile_after = json.loads(self.profile_path.read_text(encoding="utf-8"))
        self.assertNotIn(user_id, profile_after.get("web_settings", {}))
        self.assertNotIn(user_email, profile_after.get("web_settings", {}))

        me = self.client.get("/v1/auth/me")
        self.assertEqual(me.status_code, 401)


class TestDeviceOwnershipIsolation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "subscription_db.json"
        self.store = SubscriptionStore(db_path=self.db_path)
        self.store.hash_password = lambda password: _legacy_sha256(password)
        self.store.check_password = lambda password, stored_hash: stored_hash == _legacy_sha256(password)

    def tearDown(self):
        self._tmp.cleanup()

    def test_replaced_devices_do_not_leak_between_users(self):
        u1 = self.store.create_user("u1@example.com", "secret123", "U1")
        u2 = self.store.create_user("u2@example.com", "secret123", "U2")

        self.store.provision_device("bed-1", "code-1", model="x1")
        self.store.provision_device("bed-2", "code-2", model="x1")
        self.store.claim_device(u1.get("user_id", ""), "bed-1", "code-1")
        self.store.transfer_device(u1.get("user_id", ""), "bed-1", "bed-2")

        u1_ids = {d.get("device_id") for d in self.store.list_user_devices(u1.get("user_id", ""))}
        u2_ids = {d.get("device_id") for d in self.store.list_user_devices(u2.get("user_id", ""))}

        self.assertIn("bed-1", u1_ids)
        self.assertIn("bed-2", u1_ids)
        self.assertNotIn("bed-1", u2_ids)

        u2_timeline = self.store.build_user_timeline(u2.get("user_id", ""))
        leaked = [
            row
            for row in u2_timeline
            if row.get("event") == "device_replaced" and (row.get("data") or {}).get("device_id") == "bed-1"
        ]
        self.assertEqual(leaked, [])


if __name__ == "__main__":
    unittest.main()
