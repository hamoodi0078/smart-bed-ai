import os
import unittest

from fastapi.testclient import TestClient

import web_server
from time_utils import from_iso


class TestSubscriptionEndpoints(unittest.TestCase):
    def setUp(self):
        self._old_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = "sqlite://"

        web_server._DB_CONNECTION = None
        web_server._DB_CONNECTION_URL = ""
        web_server._DB_USER_REPOSITORY = None
        web_server._SUBSCRIPTION_GATE = None
        web_server._DB_SLEEP_SESSION_REPOSITORY = None
        web_server._DB_COMMAND_REPOSITORY = None

        self.user_repo = web_server._db_user_repository()
        self.user = self.user_repo.create_user("trial-endpoint@example.com", "hashed_pw", "Trial Endpoint User")
        self.client = TestClient(web_server.app)
        user_token = web_server.store.issue_user_token(user_id=self.user.id)
        self.client.cookies.set("sb_user_token", str(user_token.get("access_token", "") or ""))

    def tearDown(self):
        web_server._DB_CONNECTION = None
        web_server._DB_CONNECTION_URL = ""
        web_server._DB_USER_REPOSITORY = None
        web_server._SUBSCRIPTION_GATE = None
        web_server._DB_SLEEP_SESSION_REPOSITORY = None
        web_server._DB_COMMAND_REPOSITORY = None

        if self._old_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self._old_database_url

    def test_start_trial_returns_ok_true(self):
        response = self.client.post("/v1/subscriptions/trial/start", json={"user_id": self.user.id})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(int(body.get("days", 0)), 7)

    def test_start_trial_sets_seven_day_window(self):
        response = self.client.post("/v1/subscriptions/trial/start", json={"user_id": self.user.id})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        trial_start = from_iso(str(body.get("trial_start", "")))
        trial_end = from_iso(str(body.get("trial_end", "")))
        seconds = int((trial_end - trial_start).total_seconds())
        self.assertGreaterEqual(seconds, 604799)
        self.assertLessEqual(seconds, 604801)

    def test_start_trial_twice_returns_409(self):
        first = self.client.post("/v1/subscriptions/trial/start", json={"user_id": self.user.id})
        self.assertEqual(first.status_code, 200)

        second = self.client.post("/v1/subscriptions/trial/start", json={"user_id": self.user.id})
        self.assertEqual(second.status_code, 409)
        body = second.json()
        self.assertFalse(body.get("ok"))
        error = body.get("error", {}) if isinstance(body.get("error", {}), dict) else {}
        self.assertEqual(error.get("code"), "TRIAL_ALREADY_USED")
        self.assertRegex(str(error.get("trace_id", "")), r"^req_[a-f0-9]{8}$")
        self.assertEqual(str(second.headers.get("X-Trace-Id", "")), str(error.get("trace_id", "")))

    def test_start_trial_missing_user_id_returns_contract_error(self):
        response = self.client.post("/v1/subscriptions/trial/start", json={"user_id": ""})
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body.get("ok"))
        error = body.get("error", {}) if isinstance(body.get("error", {}), dict) else {}
        self.assertEqual(error.get("code"), "VALIDATION_ERROR")
        self.assertRegex(str(error.get("trace_id", "")), r"^req_[a-f0-9]{8}$")
        self.assertEqual(str(response.headers.get("X-Trace-Id", "")), str(error.get("trace_id", "")))

    def test_get_status_returns_subscription_status(self):
        response = self.client.get("/v1/subscriptions/status", params={"user_id": self.user.id})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get("ok"))
        self.assertIn(body.get("subscription_status"), {"free", "trial", "premium"})

    def test_get_status_free_user_has_limited_features(self):
        response = self.client.get("/v1/subscriptions/status", params={"user_id": self.user.id})
        self.assertEqual(response.status_code, 200)
        features = response.json().get("features", {})
        self.assertEqual(int(features.get("max_scenes", 0)), 3)
        self.assertEqual(int(features.get("wind_down_minutes", 0)), 10)
        self.assertEqual(int(features.get("automations_limit", 0)), 2)

    def test_get_status_trial_user_has_premium_features(self):
        start = self.client.post("/v1/subscriptions/trial/start", json={"user_id": self.user.id})
        self.assertEqual(start.status_code, 200)

        response = self.client.get("/v1/subscriptions/status", params={"user_id": self.user.id})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body.get("subscription_status"), "trial")
        self.assertTrue(body.get("trial_active"))
        features = body.get("features", {})
        self.assertEqual(int(features.get("max_scenes", 0)), 999)
        self.assertEqual(int(features.get("wind_down_minutes", 0)), 30)
        self.assertEqual(int(features.get("automations_limit", 0)), 999)


if __name__ == "__main__":
    unittest.main()
