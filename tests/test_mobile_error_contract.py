import unittest

from fastapi.testclient import TestClient

import web_server


class TestMobileErrorContract(unittest.TestCase):
    def test_mobile_settings_requires_auth_with_standard_error_envelope(self):
        client = TestClient(web_server.app)
        response = client.get("/v1/mobile/settings")
        self.assertEqual(response.status_code, 401)

        body = response.json()
        self.assertFalse(body.get("ok"))
        error = body.get("error", {}) if isinstance(body.get("error", {}), dict) else {}
        self.assertEqual(str(error.get("code", "")), "UNAUTHORIZED")
        self.assertTrue(str(error.get("message", "")).strip())
        self.assertRegex(str(error.get("trace_id", "")), r"^req_[a-f0-9]{8}$")
        self.assertEqual(str(response.headers.get("X-Trace-Id", "")), str(error.get("trace_id", "")))


if __name__ == "__main__":
    unittest.main()
