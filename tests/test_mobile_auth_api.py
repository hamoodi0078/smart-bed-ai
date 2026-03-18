import hashlib
import os
import shutil
import unittest
from contextlib import contextmanager
from pathlib import Path
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from Storage.subscription_store import SubscriptionStore
import web_server


def _legacy_sha256(password: str) -> str:
    return hashlib.sha256((password or "").encode("utf-8")).hexdigest()


@contextmanager
def _noop_io_lock(_path):
    yield


class TestMobileAuthApi(unittest.TestCase):
    def setUp(self):
        base_tmp = Path.cwd() / ".tmp"
        base_tmp.mkdir(parents=True, exist_ok=True)
        self._tmp_dir = base_tmp / f"mobile_auth_{uuid.uuid4().hex}"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self._tmp_dir / "subscription_db.json"
        self.profile_path = self._tmp_dir / "user_profile.json"
        self._sqlite_path = self._tmp_dir / "mobile_auth.sqlite3"
        self._database_url = f"sqlite:///{self._sqlite_path.as_posix()}"

        self._io_lock_patch = patch("Storage.io._path_io_lock", _noop_io_lock)
        self._patch_env = patch.dict(
            os.environ,
            {"DATABASE_URL": self._database_url},
            clear=False,
        )
        self._io_lock_patch.start()
        self.store = SubscriptionStore(db_path=self.db_path)
        self.store.hash_password = lambda password: _legacy_sha256(password)
        self.store.check_password = lambda password, stored_hash: stored_hash == _legacy_sha256(password)
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
        self._io_lock_patch.stop()
        self._patch_profile.stop()
        self._patch_store.stop()
        self._patch_env.stop()
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

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

    def test_phone_otp_request_and_verify_returns_mobile_session(self):
        request = self.client.post(
            "/v1/mobile/auth/otp/request",
            json={
                "phone_number": "+965 5000 1234",
                "client_name": "flutter_phone_auth",
            },
        )
        self.assertEqual(request.status_code, 200)
        request_body = request.json()
        self.assertTrue(request_body.get("ok"))
        request_id = str(request_body.get("request_id", "") or "")
        otp_code = str(request_body.get("debug_code", "") or "")
        self.assertTrue(request_id)
        self.assertTrue(otp_code)

        verify = self.client.post(
            "/v1/mobile/auth/otp/verify",
            json={
                "request_id": request_id,
                "phone_number": "+96550001234",
                "otp_code": otp_code,
                "name": "Phone User",
                "client_name": "flutter_phone_auth",
            },
        )
        self.assertEqual(verify.status_code, 200)
        verify_body = verify.json()
        access_token = str(verify_body.get("access_token", "") or "")
        self.assertTrue(access_token)
        self.assertEqual(
            verify_body.get("user", {}).get("client_name"),
            "flutter_phone_auth",
        )

        me = self.client.get(
            "/v1/mobile/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        self.assertEqual(me.status_code, 200)
        me_body = me.json()
        self.assertTrue(str(me_body.get("user", {}).get("email", "")).endswith("@phone.local"))

    def test_social_login_reuses_existing_identity(self):
        with patch.object(
            web_server,
            "_verify_mobile_social_identity",
            return_value={
                "provider_user_id": "social_google_user_01",
                "email": "social-user@example.com",
                "name": "Social User",
                "email_verified": True,
                "verification_method": "google_id_token",
            },
        ):
            first = self.client.post(
                "/v1/mobile/auth/social",
                json={
                    "provider": "google",
                    "provider_id_token": "mock.id.token",
                    "email": "social-user@example.com",
                    "name": "Social User",
                    "client_name": "flutter_social",
                },
            )
            self.assertEqual(first.status_code, 200)
            first_body = first.json()
            first_user_id = str(first_body.get("user", {}).get("user_id", "") or "")
            self.assertTrue(first_user_id)
            self.assertEqual(first_body.get("social_provider"), "google")
            self.assertEqual(first_body.get("social_verification"), "google_id_token")

            second = self.client.post(
                "/v1/mobile/auth/social",
                json={
                    "provider": "google",
                    "provider_id_token": "mock.id.token",
                    "email": "social-user@example.com",
                    "name": "Social User",
                    "client_name": "flutter_social",
                },
            )
            self.assertEqual(second.status_code, 200)
            second_body = second.json()
            second_user_id = str(second_body.get("user", {}).get("user_id", "") or "")
            self.assertEqual(second_user_id, first_user_id)

    def test_social_login_requires_provider_token_by_default(self):
        response = self.client.post(
            "/v1/mobile/auth/social",
            json={
                "provider": "google",
                "provider_user_id": "legacy_social_user",
                "email": "legacy-social@example.com",
                "name": "Legacy Social",
                "client_name": "flutter_social",
            },
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
