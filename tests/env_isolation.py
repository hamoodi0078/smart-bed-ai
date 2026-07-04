"""Shared test-isolation helpers.

web_server and services.auth_service cache DB connections in module-level
singletons.  Tests that patch DATABASE_URL or the subscription store must
reset these singletons in setUp AND tearDown, otherwise:

  * the cached engine keeps pointing at a previous test's (deleted) temp DB,
    causing stale reads and bogus 401s, and
  * on Windows the open sqlite file handle makes TemporaryDirectory.cleanup()
    fail with PermissionError (WinError 32).
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import services.auth_service as auth_service_module
from Storage.subscription_store import SubscriptionStore


def reset_auth_service_singleton() -> None:
    """Dispose the AuthService singleton's DB engines and force re-creation."""
    svc = auth_service_module._auth_service
    if svc is not None:
        for repo in (svc._users, svc._tokens):
            try:
                repo.db.engine.dispose()
            except Exception:
                pass
    auth_service_module._auth_service = None


def reset_web_server_db_singletons(web_server) -> None:
    """Dispose and clear all module-level DB singletons in web_server."""
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
    reset_auth_service_singleton()


class IsolatedWebAuthTestCase(unittest.TestCase):
    """Base class for web_server endpoint tests that need a logged-in cookie user.

    Provides `self.client` (TestClient) already authenticated via the cookie
    register flow, backed by a per-test temp sqlite DB and subscription store
    so tests never touch real dev data.

    Subclasses:
      * set ``premium = True`` when the endpoints under test are premium-gated
      * override ``extra_patchers()`` to add their own patch objects (started
        after the store/env patches, stopped in reverse order)
    """

    premium = False
    test_email = "endpoint-tester@example.com"
    test_password = "Endpointpass123"
    test_name = "Endpoint Tester"

    def extra_patchers(self) -> list:
        return []

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
            *self.extra_patchers(),
        ]
        for p in self._patchers:
            p.start()
        reset_web_server_db_singletons(web_server)

        self.client = TestClient(web_server.app)
        response = self.client.post(
            "/v1/auth/register",
            json={
                "email": self.test_email,
                "password": self.test_password,
                "name": self.test_name,
            },
        )
        assert response.status_code == 200, f"test user registration failed: {response.text}"
        self.user_id = str(response.json().get("user", {}).get("user_id", ""))

        if self.premium:
            web_server._db_user_repository().update_subscription(self.user_id, status="premium")

    def tearDown(self):
        reset_web_server_db_singletons(self._web_server)
        for p in reversed(self._patchers):
            p.stop()
        self._tmp.cleanup()
