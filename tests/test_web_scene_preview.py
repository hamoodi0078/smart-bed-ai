import copy
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_server


class TestWebScenePreview(unittest.TestCase):
    @patch("web_server.time.sleep")
    @patch("web_server._save_profile")
    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    def test_preview_executes_without_persisting_scene(
        self,
        mock_require_user,
        mock_safe_profile,
        _mock_save,
        _mock_sleep,
    ):
        profile = {
            "environment": {
                "last_scene_key": "balanced_default",
                "last_scene_applied_at": "2026-03-01T00:00:00+00:00",
            }
        }
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        client = TestClient(web_server.app)
        response = client.post("/v1/mobile/scenes/preview", json={"scene_key": "calm_recovery"})
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("post_preview_prompt"), "Like it? Save for Tonight")
        self.assertEqual(profile.get("environment", {}).get("last_scene_key"), "balanced_default")

    @patch("web_server.time.sleep")
    @patch("web_server._save_profile")
    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    def test_preview_does_not_increment_premium_quota(
        self,
        mock_require_user,
        mock_safe_profile,
        _mock_save,
        _mock_sleep,
    ):
        profile = {
            "premium_scene_usage": {
                "used": 7,
                "limit": 20,
            }
        }
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        client = TestClient(web_server.app)
        response = client.post("/v1/mobile/scenes/preview", json={"scene_key": "focus_momentum"})
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertTrue(body.get("premium_quota_exempt"))
        self.assertEqual(profile.get("premium_scene_usage", {}).get("used"), 7)

    @patch("web_server.time.sleep")
    @patch("web_server._save_profile")
    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    def test_preview_duration_is_capped_to_three_seconds(
        self,
        mock_require_user,
        mock_safe_profile,
        _mock_save,
        mock_sleep,
    ):
        profile: dict = {}
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        client = TestClient(web_server.app)
        response = client.post("/v1/mobile/scenes/preview", json={"scene_key": "discipline_night"})
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertEqual(float(body.get("preview_duration_seconds", 0.0)), 3.0)
        self.assertLessEqual(float(body.get("preview_duration_seconds", 0.0)), 3.0)
        mock_sleep.assert_called_once_with(3.0)

    @patch("web_server.time.sleep")
    @patch("web_server._save_profile")
    @patch("web_server._safe_profile")
    @patch("web_server._require_user")
    def test_preview_reverts_previous_led_and_audio_state(
        self,
        mock_require_user,
        mock_safe_profile,
        _mock_save,
        _mock_sleep,
    ):
        starting_controls = {
            "lights_on": False,
            "audio_on": False,
            "alarm_on": True,
            "light_level": 62,
        }
        profile = {
            "web_device_controls": {
                "u1": copy.deepcopy(starting_controls),
            }
        }
        mock_safe_profile.return_value = profile
        mock_require_user.return_value = {"user_id": "u1", "email": "u1@example.com"}

        client = TestClient(web_server.app)
        response = client.post("/v1/mobile/scenes/preview", json={"scene_key": "calm_recovery"})
        self.assertEqual(response.status_code, 200)

        restored = profile.get("web_device_controls", {}).get("u1", {})
        self.assertEqual(restored, starting_controls)


if __name__ == "__main__":
    unittest.main()
