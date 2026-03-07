import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_server


class TestWebVoiceCircuitReset(unittest.TestCase):
    def test_reset_endpoint_requires_admin(self):
        client = TestClient(web_server.app)
        response = client.post("/v1/admin/voice/circuit-breaker/reset")
        self.assertEqual(response.status_code, 401)

    @patch("web_server.store.add_admin_audit_log")
    @patch("web_server.write_voice_circuit_reset_signal")
    @patch("web_server._cookie_admin")
    def test_reset_endpoint_queues_signal(self, mock_cookie_admin, mock_write_signal, _mock_audit):
        mock_cookie_admin.return_value = {"user_id": "admin-1", "role": "owner", "email": "admin@example.com"}
        mock_write_signal.return_value = {
            "token": "123",
            "requested_at": "2026-03-07T12:00:00+00:00",
            "source": "admin_panel:admin-1",
        }

        client = TestClient(web_server.app)
        response = client.post("/v1/admin/voice/circuit-breaker/reset")
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("requested_at"), "2026-03-07T12:00:00+00:00")
        self.assertIn("queued", body.get("message", "").lower())
        mock_write_signal.assert_called_once()


if __name__ == "__main__":
    unittest.main()
