import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_server


class TestBedStateApi(unittest.TestCase):
    def test_requires_auth(self):
        client = TestClient(web_server.app)
        response = client.get("/v1/bed/state")
        self.assertEqual(response.status_code, 401)

    @patch("web_server._last_memory_context", return_value="Last memory turn: user='test'")
    @patch("web_server._safe_profile")
    @patch("web_server._cookie_user")
    def test_returns_unified_state_payload(self, mock_cookie_user, mock_safe_profile, _mock_memory):
        mock_cookie_user.return_value = {"user_id": "u1"}
        mock_safe_profile.return_value = {
            "preferences": {"personality": "therapist"},
            "personality_runtime": {"emotion_history": [{"state": "low_energy"}]},
            "adaptive_personality": {"last_selected": "guide"},
            "sleep": {
                "recovery_mode": True,
                "challenge_level": 3,
                "night_wake_count": 2,
                "bedtime_history": ["22:30"],
                "wake_history": ["07:00"],
                "partner_mode": {"enabled": True},
                "last_bedtime_drift_alert_date": "2026-02-24",
            },
            "hardware": {
                "user_strip_pin": 18,
                "state_strip_pin": 13,
                "user_strip_led_count": 120,
                "state_strip_led_count": 60,
            },
            "environment": {
                "last_scene_key": "balanced_default",
                "last_preload_phase": "sleep",
            },
            "runtime_flags": {
                "sensor_pressure_active": False,
                "sensor_motion_active": True,
            },
            "spotify_tokens": {"u1": {"access_token": "x"}},
        }

        client = TestClient(web_server.app)
        response = client.get("/v1/bed/state")
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("emotion_state"), "low_energy")
        self.assertEqual(body.get("active_personality"), "guide")
        self.assertIn("Last memory turn", body.get("last_memory_context", ""))

        biometric = body.get("biometric_summary", {})
        self.assertTrue(biometric.get("recovery_mode"))
        self.assertEqual(biometric.get("challenge_level"), 3)

        device = body.get("device_health_status", {})
        self.assertIn("led", device)
        self.assertEqual(device.get("last_preload_phase"), "sleep")

    @patch("web_server._safe_profile")
    @patch("web_server._cookie_user")
    @patch("web_server._device_health_status")
    def test_v1_state_redacts_sensitive_tokens(self, mock_device_health, mock_cookie_user, mock_safe_profile):
        mock_cookie_user.return_value = {"user_id": "u1"}
        mock_safe_profile.return_value = {"preferences": {"personality": "guide"}}
        mock_device_health.return_value = {
            "spotify_connected_users": 1,
            "access_token": "secret-a",
            "refresh_token": "secret-r",
            "password_hash": "secret-h",
            "oauth_token": "secret-oauth",
            "nested": {
                "oauth_access_token": "nested-secret",
                "ok": True,
            },
        }

        client = TestClient(web_server.app)
        response = client.get("/v1/state")
        self.assertEqual(response.status_code, 200)

        snapshot = response.json().get("snapshot", {})
        self.assertIn("device_health_status", snapshot)
        payload = str(snapshot).lower()
        self.assertNotIn("access_token", payload)
        self.assertNotIn("refresh_token", payload)
        self.assertNotIn("password_hash", payload)
        self.assertNotIn("oauth_token", payload)
        self.assertTrue(snapshot.get("device_health_status", {}).get("nested", {}).get("ok"))

    @patch("web_server._generate_actor_reply", return_value=("Sure. I can help with that.", False))
    @patch("web_server._cookie_user")
    def test_v1_command_basic_success_response(self, mock_cookie_user, _mock_reply):
        mock_cookie_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        client = TestClient(web_server.app)
        response = client.post(
            "/v1/command",
            json={"text": "start wind down", "source": "web"},
        )
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertIn("reply_text", body)
        self.assertEqual(body.get("reply_text"), "Sure. I can help with that.")
        self.assertIn("effects_summary", body)
        effects = body.get("effects_summary", {})
        self.assertEqual(effects.get("source"), "web")
        self.assertIn("executed_actions", effects)
        self.assertIn("assistant_fallback_used", effects)


if __name__ == "__main__":
    unittest.main()
