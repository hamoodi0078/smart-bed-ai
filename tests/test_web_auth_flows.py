import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from Storage.subscription_store import SubscriptionStore
from time_utils import from_iso, utcnow
import services.auth_service as auth_service_module
import web_server


def _legacy_sha256(password: str) -> str:
    return hashlib.sha256((password or "").encode("utf-8")).hexdigest()


def _reset_auth_service_singleton() -> None:
    """Dispose the AuthService singleton's DB engines and force re-creation.

    The singleton caches repositories bound to whichever DATABASE_URL was
    active when it was first used.  Without this reset it keeps the previous
    test's temp sqlite file open, which breaks the test (stale engine) and
    the temp-dir cleanup on Windows (file lock).
    """
    svc = auth_service_module._auth_service
    if svc is not None:
        for repo in (svc._users, svc._tokens):
            try:
                repo.db.engine.dispose()
            except Exception:
                pass
    auth_service_module._auth_service = None


class TestWebAuthFlows(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmp.name) / "subscription_db.json"
        self.profile_path = Path(self._tmp.name) / "user_profile.json"
        self.sqlite_path = Path(self._tmp.name) / "web_auth.sqlite3"
        self.database_url = f"sqlite:///{self.sqlite_path.as_posix()}"
        self.store = SubscriptionStore(db_path=self.db_path)

        # Keep auth tests independent from optional bcrypt installation state.
        self.store.hash_password = lambda password: _legacy_sha256(password)
        self.store.check_password = lambda password, stored_hash: (
            stored_hash == _legacy_sha256(password)
        )

        self._patch_env = patch.dict(
            os.environ,
            {"DATABASE_URL": self.database_url},
            clear=False,
        )
        self._patch_store = patch.object(web_server, "store", self.store)
        self._patch_profile = patch.object(web_server, "PROFILE_PATH", self.profile_path)
        self._patch_env.start()
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
        web_server._DB_MOBILE_AUTH_REPOSITORY = None
        _reset_auth_service_singleton()
        self.client = TestClient(web_server.app)

    def tearDown(self):
        connection = getattr(web_server, "_DB_CONNECTION", None)
        if connection is not None:
            try:
                connection.engine.dispose()
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
        web_server._DB_MOBILE_AUTH_REPOSITORY = None
        _reset_auth_service_singleton()
        self._patch_profile.stop()
        self._patch_store.stop()
        self._patch_env.stop()
        self._tmp.cleanup()

    def _register(
        self, email: str = "user@example.com", password: str = "Secret1234", name: str = "User"
    ):
        return self.client.post(
            "/v1/auth/register",
            json={"email": email, "password": password, "name": name},
        )

    def _login(self, email: str = "user@example.com", password: str = "Secret1234"):
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
        self._register(email="login@example.com", password="Letmein12345")
        self.client.post("/v1/auth/logout")

        response = self._login(email="login@example.com", password="Letmein12345")
        self.assertEqual(response.status_code, 200)
        me = self.client.get("/v1/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json().get("user", {}).get("email"), "login@example.com")

    def test_user_session_expiry_math_uses_aware_utc(self):
        created = self.store.create_user("expiry@example.com", "letmein1", "Expiry")
        token_bundle = self.store.issue_user_token(created.get("user_id", ""), ttl_hours=1)

        expires_at = from_iso(token_bundle.get("expires_at", ""))
        self.assertIsNotNone(expires_at.tzinfo)
        self.assertEqual(expires_at.utcoffset().total_seconds(), 0)

        remaining = (expires_at - utcnow()).total_seconds()
        self.assertGreater(remaining, 3500)
        self.assertLessEqual(remaining, 3600)

    def test_admin_bootstrap_does_not_auto_promote_owner(self):
        register = self._register(email="admin-bootstrap@example.com", password="Letmein12345")
        user_id = register.json().get("user", {}).get("user_id")

        response = self.client.post(
            "/v1/admin/auth/login",
            json={"email": "admin-bootstrap@example.com", "password": "Letmein12345"},
        )
        self.assertEqual(response.status_code, 403)

        admin_row = self.store.get_admin_user(user_id)
        self.assertIsNotNone(admin_row)
        self.assertEqual(admin_row.get("role"), "viewer")

    def test_logout_revokes_server_session(self):
        self._register(email="logout@example.com", password="Letmein12345")
        token = self.client.cookies.get("sb_user_token")
        self.assertIn(token, self.store.db.get("user_sessions", {}))

        response = self.client.post("/v1/auth/logout")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(token, self.store.db.get("user_sessions", {}))

        me = self.client.get("/v1/auth/me")
        self.assertEqual(me.status_code, 401)

    def test_delete_data_removes_user_profile_and_sessions(self):
        register = self._register(email="delete@example.com", password="Letmein12345")
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
        self.assertFalse(
            any(
                s.get("user_id") == user_id for s in self.store.db.get("user_sessions", {}).values()
            )
        )
        self.assertFalse(
            any(
                s.get("user_id") == user_id
                for s in self.store.db.get("admin_sessions", {}).values()
            )
        )

        profile_after = json.loads(self.profile_path.read_text(encoding="utf-8"))
        self.assertNotIn(user_id, profile_after.get("web_settings", {}))
        self.assertNotIn(user_email, profile_after.get("web_settings", {}))

        me = self.client.get("/v1/auth/me")
        self.assertEqual(me.status_code, 401)


class TestDeviceOwnershipIsolation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmp.name) / "subscription_db.json"
        self.store = SubscriptionStore(db_path=self.db_path)
        self.store.hash_password = lambda password: _legacy_sha256(password)
        self.store.check_password = lambda password, stored_hash: (
            stored_hash == _legacy_sha256(password)
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_replaced_devices_do_not_leak_between_users(self):
        u1 = self.store.create_user("u1@example.com", "Secret1234", "U1")
        u2 = self.store.create_user("u2@example.com", "Secret1234", "U2")

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
            if row.get("event") == "device_replaced"
            and (row.get("data") or {}).get("device_id") == "bed-1"
        ]
        self.assertEqual(leaked, [])


if __name__ == "__main__":
    unittest.main()
