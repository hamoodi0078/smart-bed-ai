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


if __name__ == "__main__":
    unittest.main()
