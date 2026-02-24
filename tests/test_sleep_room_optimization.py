import unittest
from unittest.mock import MagicMock, patch

from ai.environment_orchestrator import EnvironmentOrchestrator
from ai.sleep_intelligence import SleepIntelligenceEngine
from main import handle_local_commands


class TestSleepRoomOptimization(unittest.TestCase):
    def _call(self, user_text: str, profile: dict, spotify_result: tuple[bool, str], local_result: tuple[bool, str]):
        led = MagicMock()
        spotify = MagicMock()
        spotify.play_track_query.return_value = spotify_result
        local_music = MagicMock()
        local_music.play_query.return_value = local_result

        response, handled = handle_local_commands(
            user_text=user_text,
            profile=profile,
            led=led,
            spotify=spotify,
            local_music=local_music,
            schedule=MagicMock(),
            goal_manager=MagicMock(),
            daily_life_support=MagicMock(),
            goal_compass=MagicMock(),
            sleep_engine=SleepIntelligenceEngine(),
            environment_orchestrator=EnvironmentOrchestrator(),
            runtime_orchestrator=MagicMock(),
            goal_strategy=MagicMock(),
            sleep_routine=MagicMock(),
            routine_engine=MagicMock(),
            tts_player=MagicMock(),
            audio_output=MagicMock(),
            backend_client=MagicMock(),
            health_report_builder=lambda: "ok",
            on_sleep_timer_finish=lambda: None,
            breathing_guide=MagicMock(),
            dream_journal=MagicMock(),
            adaptive_personality=MagicMock(),
            tts=MagicMock(),
            wake_word_manager=MagicMock(),
        )
        return response, handled, profile

    @patch("main.save_profile")
    def test_optimize_room_for_sleep_applies_scene_and_autopilot(self, _mock_save_profile):
        profile = {"preferences": {}, "sleep": {"wind_down_minutes": 30}, "runtime_flags": {}}

        response, handled, updated = self._call(
            user_text="optimize my room for sleep",
            profile=profile,
            spotify_result=(False, "Spotify unavailable"),
            local_result=(True, "Playing local sleep track."),
        )

        self.assertTrue(handled)
        self.assertIn("Environment scene: sleep optimization.", response)
        self.assertIn("Wind-down autopilot enabled", response)
        self.assertIn("Playing local sleep track.", response)
        self.assertEqual(updated.get("environment", {}).get("last_scene_key"), "sleep_optimized_room")
        self.assertTrue(bool(updated.get("sleep", {}).get("wind_down_enabled")))

    @patch("main.save_profile")
    def test_optimize_room_for_sleep_has_audio_fallback_message(self, _mock_save_profile):
        profile = {"preferences": {}, "sleep": {}, "runtime_flags": {}}

        response, handled, _updated = self._call(
            user_text="optimize room for sleep",
            profile=profile,
            spotify_result=(False, ""),
            local_result=(False, ""),
        )

        self.assertTrue(handled)
        self.assertIn("room settings are optimized", response)


if __name__ == "__main__":
    unittest.main()
