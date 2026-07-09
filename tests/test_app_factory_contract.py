"""Contract tests against the PRODUCTION app (api.app_factory:app).

These exist because production serves app_factory while the legacy tests
exercise web_server.app — the seam where the 2026-07-08 audit found all
three P0 bugs. Every mobile-facing contract fix lands here first.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from Storage.subscription_store import SubscriptionStore
from tests.env_isolation import reset_web_server_db_singletons


class AppFactoryContractCase(unittest.TestCase):
    """TestClient against api.app_factory.app with per-test sqlite isolation.

    Mirrors tests/env_isolation.py::IsolatedWebAuthTestCase, but drives the
    production app instead of web_server.app. web_server is still imported
    and patched because migrated routers lazy-import handlers from it.
    """

    test_password = "Contractpass123"
    test_name = "Contract Tester"

    def setUp(self):
        import web_server

        self._web_server = web_server
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        tmp = Path(self._tmp.name)
        self._patchers = [
            patch.dict(
                os.environ,
                {"DATABASE_URL": f"sqlite:///{(tmp / 'test.sqlite3').as_posix()}"},
                clear=False,
            ),
            patch.object(
                web_server, "store", SubscriptionStore(db_path=tmp / "subscription_db.json")
            ),
        ]
        for p in self._patchers:
            p.start()
        reset_web_server_db_singletons(web_server)

        from api.app_factory import app

        # Plain TestClient (no context manager): lifespan is intentionally not
        # run, so Sentry/arq/async-DB init never fire in tests.
        self.client = TestClient(app)

    def tearDown(self):
        reset_web_server_db_singletons(self._web_server)
        for p in reversed(self._patchers):
            p.stop()
        self._tmp.cleanup()

    # ── helpers ───────────────────────────────────────────────────────────────

    def register(self, email: str = "contract-tester@example.com") -> dict:
        resp = self.client.post(
            "/v1/mobile/auth/register",
            json={"email": email, "password": self.test_password, "name": self.test_name},
        )
        assert resp.status_code == 200, f"register failed: {resp.text}"
        return resp.json()

    def bearer(self, auth: dict) -> dict:
        return {"Authorization": f"Bearer {auth['access_token']}"}


class AuthWalkTests(AppFactoryContractCase):
    def test_register_login_me_dashboard(self):
        auth = self.register()
        self.assertTrue(auth["access_token"])
        self.assertTrue(auth["refresh_token"])
        user_id = auth["user"]["user_id"]
        self.assertTrue(user_id)

        resp = self.client.post(
            "/v1/mobile/auth/login",
            json={"email": "contract-tester@example.com", "password": self.test_password},
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        headers = self.bearer(resp.json())
        resp = self.client.get("/v1/mobile/auth/me", headers=headers)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["user"]["user_id"], user_id)

        # Dashboard triggers the lazy web_server import — the full production path
        resp = self.client.get("/v1/mobile/dashboard", headers=headers)
        self.assertEqual(resp.status_code, 200, resp.text)


class AlarmContractTests(AppFactoryContractCase):
    """The Flutter contract — mirrors AlarmSchedule.toJson()/fromJson() and
    api_client.dart upsertAlarm(), which expects {"alarms": [...]} back."""

    APP_PAYLOAD = {
        "alarm_id": "",
        "time": "06:30",
        "days": [1, 2, 3],  # ISO weekdays: Mon, Tue, Wed
        "enabled": True,
        "label": "Fajr",
        "sound": "default",
        "vibrate": True,
    }

    def test_create_list_edit_toggle_delete_roundtrip(self):
        auth = self.register("alarm-tester@example.com")
        headers = self.bearer(auth)

        # Create — app expects the FULL refreshed list back
        resp = self.client.post("/v1/mobile/alarms", json=self.APP_PAYLOAD, headers=headers)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertIn("alarms", body, f"POST must return the alarm list, got: {body}")
        self.assertEqual(len(body["alarms"]), 1)
        alarm = body["alarms"][0]
        self.assertTrue(alarm["alarm_id"], "alarm_id must be non-empty")
        self.assertEqual(alarm["days"], [1, 2, 3])
        self.assertEqual(alarm["sound"], "default")
        self.assertTrue(alarm["vibrate"])
        alarm_id = alarm["alarm_id"]

        resp = self.client.get("/v1/mobile/alarms", headers=headers)
        self.assertEqual(resp.json()["alarms"][0]["alarm_id"], alarm_id)

        # Edit via POST upsert (the app always POSTs) — must NOT duplicate
        edited = {**self.APP_PAYLOAD, "alarm_id": alarm_id, "label": "Fajr prayer"}
        resp = self.client.post("/v1/mobile/alarms", json=edited, headers=headers)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(len(body["alarms"]), 1, "edit must not create a duplicate")
        self.assertEqual(body["alarms"][0]["label"], "Fajr prayer")

        resp = self.client.post(
            f"/v1/mobile/alarms/{alarm_id}/toggle", json={"enabled": False}, headers=headers
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        resp = self.client.delete(f"/v1/mobile/alarms/{alarm_id}", headers=headers)
        self.assertEqual(resp.status_code, 200, resp.text)
        resp = self.client.get("/v1/mobile/alarms", headers=headers)
        self.assertEqual(resp.json()["alarms"], [])

    def test_unknown_alarm_id_is_404_not_duplicate(self):
        auth = self.register("alarm-tester-2@example.com")
        payload = {**self.APP_PAYLOAD, "alarm_id": "no-such-alarm"}
        resp = self.client.post("/v1/mobile/alarms", json=payload, headers=self.bearer(auth))
        self.assertEqual(resp.status_code, 404, resp.text)


class SharedConnectionTests(AppFactoryContractCase):
    def test_repositories_share_one_engine(self):
        from database import AlarmRepository
        from database.connection import get_shared_connection

        a, b = AlarmRepository(), AlarmRepository()
        self.assertIs(a.db.engine, b.db.engine)
        self.assertIs(a.db.engine, get_shared_connection().engine)


class AdminContractTests(AppFactoryContractCase):
    """The web panel authenticates with the sb_admin_token cookie
    (web/assets/app.js sends credentials:"include", never a Bearer header)."""

    def test_cookie_login_then_protected_endpoints(self):
        auth = self.register("admin-tester@example.com")
        user_id = auth["user"]["user_id"]
        # Admin role records live in the subscription store today
        self._web_server.store.upsert_admin_user(
            user_id, "admin-tester@example.com", role="admin"
        )
        resp = self.client.post(
            "/v1/admin/auth/login",
            json={"email": "admin-tester@example.com", "password": self.test_password},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["admin"]["role"], "admin")

        # The cookie session must now open protected admin routes (P0-2:
        # today these 401 because the router demands a Bearer role JWT)
        resp = self.client.get("/v1/admin/overview")
        self.assertEqual(resp.status_code, 200, resp.text)
        resp = self.client.get("/v1/admin/auth/me")
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_anonymous_admin_calls_are_rejected(self):
        resp = self.client.get("/v1/admin/overview")
        self.assertEqual(resp.status_code, 401, resp.text)


class TokenRevocationTests(AppFactoryContractCase):
    def test_logout_revokes_access_token_on_migrated_routes(self):
        auth = self.register("revoke-tester@example.com")
        headers = self.bearer(auth)
        self.assertEqual(self.client.get("/v1/mobile/auth/me", headers=headers).status_code, 200)

        resp = self.client.post(
            "/v1/mobile/auth/logout",
            json={"refresh_token": auth["refresh_token"]},
            headers=headers,
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        # The old access token must now be rejected on every migrated route
        self.assertEqual(self.client.get("/v1/mobile/auth/me", headers=headers).status_code, 401)
        self.assertEqual(self.client.get("/v1/mobile/alarms", headers=headers).status_code, 401)


class ProfileReadThroughTests(AppFactoryContractCase):
    """P0-3: what the app saves via POST /v1/mobile/profile must drive
    prayer times, dashboard identity, and chat context — not the legacy
    JSON that nothing writes anymore."""

    PROFILE = {
        "display_name": "Danah",
        "location_mode": "auto",
        "latitude": 29.3759,
        "longitude": 47.9774,
        "city": "Kuwait City",
        "country_code": "KW",
    }

    def _save_profile(self, email: str) -> dict:
        auth = self.register(email)
        resp = self.client.post("/v1/mobile/profile", json=self.PROFILE, headers=self.bearer(auth))
        self.assertEqual(resp.status_code, 200, resp.text)
        return auth

    def test_saved_profile_drives_prayer_location(self):
        auth = self._save_profile("profile-tester@example.com")
        from api.routers.islamic import _prayer_location

        loc = _prayer_location({"user_id": auth["user"]["user_id"]}, profile={})
        self.assertEqual(loc["latitude"], 29.3759)
        self.assertEqual(loc["longitude"], 47.9774)
        self.assertEqual(loc["mode"], "auto")

    def test_chat_prefs_read_db_first(self):
        auth = self._save_profile("profile-tester-2@example.com")
        prefs = self._web_server._chat_profile_prefs_for_user(
            {}, {"user_id": auth["user"]["user_id"]}
        )
        self.assertEqual(prefs["display_name"], "Danah")

    def test_islamic_overview_not_premium_gated(self):
        auth = self.register("free-tester@example.com")
        with patch.object(
            self._web_server, "_mobile_islamic_overview_payload", return_value={"islamic": {}}
        ):
            resp = self.client.get("/v1/mobile/islamic/overview", headers=self.bearer(auth))
        self.assertEqual(resp.status_code, 200, resp.text)


class JwtRoleClaimTests(unittest.TestCase):
    def test_role_claim_roundtrip(self):
        from datetime import datetime, timedelta, timezone

        from auth.jwt_handler import create_access_token, decode_access_token

        exp = datetime.now(timezone.utc) + timedelta(minutes=5)
        token = create_access_token(user_id="u1", jti="j1", exp=exp, role="admin")
        self.assertEqual(decode_access_token(token)["role"], "admin")

        token = create_access_token(user_id="u1", jti="j2", exp=exp)
        self.assertNotIn("role", decode_access_token(token))


if __name__ == "__main__":
    unittest.main()
