import importlib
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import config
import web_server


class TestConfigFromEnvironment(unittest.TestCase):
    def test_settings_reads_environment_values(self):
        try:
            with patch.dict(
                os.environ,
                {
                    "WEB_ALLOWED_ORIGINS": "http://localhost:9100",
                    "DEEPGRAM_API_KEY": "dg_test_key",
                    "SPOTIFY_CLIENT_ID": "spotify_test_client",
                },
                clear=False,
            ):
                reloaded = importlib.reload(config)
                self.assertEqual(reloaded.settings.web_allowed_origins_raw, "http://localhost:9100")
                self.assertEqual(reloaded.settings.deepgram_api_key, "dg_test_key")
                self.assertEqual(reloaded.settings.spotify_client_id, "spotify_test_client")
        finally:
            importlib.reload(config)


class TestMetricsEndpoint(unittest.TestCase):
    def test_metrics_endpoint_is_available(self):
        client = TestClient(web_server.app)
        response = client.get("/metrics")
        self.assertEqual(response.status_code, 200)
        content_type = response.headers.get("content-type", "")
        self.assertIn("text/plain", content_type)

    def test_metrics_output_includes_expected_families(self):
        client = TestClient(web_server.app)
        client.get("/healthz")
        client.get("/v1/bed/state")
        metrics_response = client.get("/metrics")
        self.assertEqual(metrics_response.status_code, 200)
        payload = metrics_response.text
        self.assertIn("smart_bed_http_requests_total", payload)
        self.assertIn("smart_bed_http_request_latency_seconds", payload)
        self.assertIn("smart_bed_http_errors_total", payload)


if __name__ == "__main__":
    unittest.main()
