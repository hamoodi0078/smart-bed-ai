import re
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_server


class TestWebLastCommandResult(unittest.TestCase):
    @patch("web_server._save_profile")
    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    def test_last_command_result_stored_after_execution(
        self, mock_require_user, mock_safe_profile, _mock_save
    ):
        profile: dict = {}
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        client = TestClient(web_server.app)
        create_response = client.post("/v1/mobile/device-commands", json={"action": "winddown"})
        self.assertEqual(create_response.status_code, 200)
        create_body = create_response.json()
        command_id = str(create_body.get("command_id", ""))
        self.assertTrue(command_id)

        profile["web_device_commands"]["u1"][0]["created_at"] = "2026-03-01T00:00:00+00:00"
        status_response = client.get(f"/v1/mobile/device-commands/{command_id}")
        self.assertEqual(status_response.status_code, 200)
        status_body = status_response.json()

        last_result = status_body.get("last_command_result", {})
        self.assertTrue(last_result.get("success"))
        self.assertEqual(str(last_result.get("status", "")).lower(), "completed")
        persisted = profile.get("web_last_command_result", {}).get("u1", {})
        self.assertTrue(persisted.get("success"))

    @patch("web_server._save_profile")
    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    def test_dashboard_payload_includes_status_and_timestamp(
        self, mock_require_user, mock_safe_profile, _mock_save
    ):
        profile: dict = {}
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        client = TestClient(web_server.app)
        client.post("/v1/mobile/device-commands", json={"action": "optimize_room"})
        dashboard_response = client.get("/v1/mobile/dashboard")
        self.assertEqual(dashboard_response.status_code, 200)

        last_result = dashboard_response.json().get("last_command_result", {})
        self.assertIn(
            str(last_result.get("status", "")), {"queued", "running", "completed", "failed"}
        )
        self.assertTrue(str(last_result.get("timestamp_utc", "")).strip())

    @patch("web_server._save_profile")
    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    def test_retry_uses_same_action(self, mock_require_user, mock_safe_profile, _mock_save):
        profile: dict = {}
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        client = TestClient(web_server.app)
        first = client.post("/v1/mobile/device-commands", json={"action": "wake_recovery"})
        self.assertEqual(first.status_code, 200)
        first_body = first.json()

        retry_action = str(first_body.get("last_command_result", {}).get("retry_action", ""))
        self.assertEqual(retry_action, "wake_recovery")

        second = client.post("/v1/mobile/device-commands", json={"action": retry_action})
        self.assertEqual(second.status_code, 200)
        second_body = second.json()
        self.assertEqual(str(second_body.get("action", "")), "wake_recovery")
        self.assertNotEqual(
            str(first_body.get("command_id", "")), str(second_body.get("command_id", ""))
        )

    @patch("web_server._save_profile")
    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    def test_trace_id_available_for_details_view(
        self, mock_require_user, mock_safe_profile, _mock_save
    ):
        profile: dict = {}
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        client = TestClient(web_server.app)
        create_response = client.post(
            "/v1/mobile/device-commands", json={"action": "reactive_lights"}
        )
        self.assertEqual(create_response.status_code, 200)
        create_body = create_response.json()
        command_id = str(create_body.get("command_id", ""))

        initial_trace = str(create_body.get("last_command_result", {}).get("trace_id", ""))
        self.assertRegex(initial_trace, r"^req_[a-f0-9]{8}$")

        profile["web_device_commands"]["u1"][0]["created_at"] = "2026-03-01T00:00:00+00:00"
        status_response = client.get(f"/v1/mobile/device-commands/{command_id}")
        self.assertEqual(status_response.status_code, 200)
        status_trace = str(
            status_response.json().get("last_command_result", {}).get("trace_id", "")
        )
        self.assertRegex(status_trace, r"^req_[a-f0-9]{8}$")

        dashboard_response = client.get("/v1/mobile/dashboard")
        self.assertEqual(dashboard_response.status_code, 200)
        dashboard_trace = str(
            dashboard_response.json().get("last_command_result", {}).get("trace_id", "")
        )
        self.assertRegex(dashboard_trace, r"^req_[a-f0-9]{8}$")


if __name__ == "__main__":
    unittest.main()
