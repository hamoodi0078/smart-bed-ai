import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from Storage.subscription_store import SubscriptionStore
import web_server


def _legacy_sha256(password: str) -> str:
    return hashlib.sha256((password or "").encode("utf-8")).hexdigest()


class TestMobileAuthApi(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "subscription_db.json"
        self.profile_path = Path(self._tmp.name) / "user_profile.json"
        self._sqlite_path = Path(self._tmp.name) / "mobile_auth.sqlite3"
        self._database_url = f"sqlite:///{self._sqlite_path.as_posix()}"
        self.store = SubscriptionStore(db_path=self.db_path)
        self.store.hash_password = lambda password: _legacy_sha256(password)
        self.store.check_password = lambda password, stored_hash: stored_hash == _legacy_sha256(password)

        self._patch_env = patch.dict(
            os.environ,
            {"DATABASE_URL": self._database_url},
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
        self._patch_profile.stop()
        self._patch_store.stop()
        self._patch_env.stop()
        self._tmp.cleanup()

    def test_register_returns_bearer_tokens_and_me_works(self):
        response = self.client.post(
            "/v1/mobile/auth/register",
            json={
                "email": "mobile@example.com",
                "password": "secret123",
                "name": "Mobile User",
                "client_name": "flutter_debug",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("token_type"), "Bearer")
        access_token = str(body.get("access_token", ""))
        refresh_token = str(body.get("refresh_token", ""))
        self.assertTrue(access_token)
        self.assertTrue(refresh_token)
        # Step 5 target: mobile bearer sessions are DB-backed, not JSON-backed.
        self.assertEqual(self.store.db.get("mobile_sessions", {}), {})
        self.assertEqual(self.store.db.get("mobile_refresh_sessions", {}), {})

        me = self.client.get(
            "/v1/mobile/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        self.assertEqual(me.status_code, 200)
        me_body = me.json()
        self.assertEqual(me_body.get("user", {}).get("email"), "mobile@example.com")
        self.assertEqual(me_body.get("user", {}).get("client_name"), "flutter_debug")

    def test_mobile_access_works_after_legacy_session_maps_are_cleared(self):
        register = self.client.post(
            "/v1/mobile/auth/register",
            json={"email": "dbsession@example.com", "password": "secret123", "name": "DB Session User"},
        )
        self.assertEqual(register.status_code, 200)
        body = register.json()
        access_token = str(body.get("access_token", ""))
        refresh_token = str(body.get("refresh_token", ""))
        self.assertTrue(access_token)
        self.assertTrue(refresh_token)

        self.store.db["mobile_sessions"] = {}
        self.store.db["mobile_refresh_sessions"] = {}
        self.store.save()

        me = self.client.get(
            "/v1/mobile/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        self.assertEqual(me.status_code, 200)

        refreshed = self.client.post(
            "/v1/mobile/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        self.assertEqual(refreshed.status_code, 200)
        refreshed_body = refreshed.json()
        self.assertNotEqual(str(refreshed_body.get("access_token", "")), access_token)

    def test_mobile_bearer_can_call_existing_mobile_endpoints(self):
        register = self.client.post(
            "/v1/mobile/auth/register",
            json={"email": "settings@example.com", "password": "secret123", "name": "Settings User"},
        )
        access_token = str(register.json().get("access_token", ""))
        headers = {"Authorization": f"Bearer {access_token}"}

        update = self.client.post(
            "/v1/mobile/settings",
            json={
                "response_style": "calm",
                "engagement_level": "low",
                "wind_down_minutes": 20,
                "partner_mode_enabled": False,
                "bedtime_drift_automation_enabled": False,
                "quiet_hours_override_limit_minutes": 45,
                "weekly_insight_enabled": False,
            },
            headers=headers,
        )
        self.assertEqual(update.status_code, 200)
        self.assertTrue(update.json().get("ok"))

        fetch = self.client.get("/v1/mobile/settings", headers=headers)
        self.assertEqual(fetch.status_code, 200)
        settings = fetch.json().get("settings", {})
        self.assertEqual(settings.get("response_style"), "calm")
        self.assertEqual(int(settings.get("wind_down_minutes", 0)), 20)
        self.assertFalse(bool(settings.get("bedtime_drift_automation_enabled", True)))
        self.assertEqual(int(settings.get("quiet_hours_override_limit_minutes", 0)), 45)
        self.assertFalse(bool(settings.get("weekly_insight_enabled", True)))

    def test_refresh_rotates_mobile_session_and_logout_revokes_access(self):
        register = self.client.post(
            "/v1/mobile/auth/register",
            json={"email": "refresh@example.com", "password": "secret123", "name": "Refresh User"},
        )
        register_body = register.json()
        old_access_token = str(register_body.get("access_token", ""))
        refresh_token = str(register_body.get("refresh_token", ""))

        refresh = self.client.post(
            "/v1/mobile/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        self.assertEqual(refresh.status_code, 200)
        refresh_body = refresh.json()
        new_access_token = str(refresh_body.get("access_token", ""))
        new_refresh_token = str(refresh_body.get("refresh_token", ""))
        self.assertNotEqual(old_access_token, new_access_token)
        self.assertNotEqual(refresh_token, new_refresh_token)

        settings = self.client.get(
            "/v1/mobile/settings",
            headers={"Authorization": f"Bearer {new_access_token}"},
        )
        self.assertEqual(settings.status_code, 200)

        logout = self.client.post(
            "/v1/mobile/auth/logout",
            json={"refresh_token": new_refresh_token},
            headers={"Authorization": f"Bearer {new_access_token}"},
        )
        self.assertEqual(logout.status_code, 200)
        self.assertTrue(logout.json().get("ok"))

        me = self.client.get(
            "/v1/mobile/auth/me",
            headers={"Authorization": f"Bearer {new_access_token}"},
        )
        self.assertEqual(me.status_code, 401)

    def test_login_migrates_legacy_only_user_into_db_shadow(self):
        legacy_hash = _legacy_sha256("secret123")
        legacy_user = {
            "user_id": "usr_legacy_sync",
            "email": "legacy-only@example.com",
            "name": "Legacy Only",
            "password_hash": legacy_hash,
            "created_at": "2026-03-01T00:00:00Z",
        }
        self.store.db["users"].append(legacy_user)
        self.store.db["subscriptions"].append(
            {
                "user_id": legacy_user["user_id"],
                "tier": "free",
                "interval": "monthly",
                "status": "active",
                "payment_provider": "none",
                "price_kwd": 0.0,
                "next_renewal_at": "",
                "grace_end_at": "",
                "updated_at": "2026-03-01T00:00:00Z",
            }
        )
        self.store.save()

        login = self.client.post(
            "/v1/mobile/auth/login",
            json={"email": "legacy-only@example.com", "password": "secret123", "client_name": "flutter_migrate"},
        )
        self.assertEqual(login.status_code, 200)
        body = login.json()
        self.assertEqual(body.get("user", {}).get("user_id"), "usr_legacy_sync")

        db_user = web_server._db_user_repository().get_user_by_id("usr_legacy_sync")
        self.assertIsNotNone(db_user)
        self.assertEqual(str(getattr(db_user, "email", "") or ""), "legacy-only@example.com")
        self.assertEqual(str(getattr(db_user, "password_hash", "") or ""), legacy_hash)


if __name__ == "__main__":
    unittest.main()
