import unittest
from unittest.mock import patch

from ai.wake_word_manager import WakeWordManager
from main import (
    _is_scene_clarification_candidate,
    _is_session_end_command,
    _is_simple_yes,
    _resolve_scene_clarification_followup,
    get_query_text,
)


class _FakeWakeWordManager:
    def __init__(self, voice_available=True, heard=None, confirmations=None):
        self._voice_available = bool(voice_available)
        self._heard = list(heard or [])
        self._confirmations = list(confirmations or [])

    def is_voice_available(self):
        return self._voice_available

    def get_user_text_with_confidence(self):
        if not self._heard:
            return "", 0.0
        return self._heard.pop(0)

    def get_user_text(self):
        if not self._confirmations:
            return ""
        return self._confirmations.pop(0)


class _FakeSTTManager:
    def __init__(self, transcript="", confidence=0.0):
        self.transcript = transcript
        self.confidence = confidence

    def transcribe_file_with_confidence(self, _audio_path):
        return self.transcript, self.confidence


class TestListeningConfidence(unittest.TestCase):
    def test_wake_word_manager_allows_unlimited_phrase_limit_with_zero(self):
        manager = WakeWordManager(
            mode="keyboard",
            wake_word="hey smart bed",
            voice_phrase_limit_seconds=0,
            barge_in_phrase_limit_seconds=0,
        )

        self.assertIsNone(manager.voice_phrase_limit_seconds)
        self.assertIsNone(manager.barge_in_phrase_limit_seconds)

    def test_wake_word_manager_clamps_positive_phrase_limit_to_min_two(self):
        manager = WakeWordManager(
            mode="keyboard",
            wake_word="hey smart bed",
            voice_phrase_limit_seconds=1,
            barge_in_phrase_limit_seconds=1,
        )

        self.assertEqual(manager.voice_phrase_limit_seconds, 2)
        self.assertEqual(manager.barge_in_phrase_limit_seconds, 2)

    def test_barge_in_sanitizer_rejects_low_confidence_short_fragment(self):
        manager = WakeWordManager(mode="keyboard", wake_word="hey smart bed")

        cleaned = manager._sanitize_barge_in_text("how", 0.41)

        self.assertEqual(cleaned, "")

    def test_barge_in_sanitizer_accepts_clear_question(self):
        manager = WakeWordManager(mode="keyboard", wake_word="hey smart bed")

        cleaned = manager._sanitize_barge_in_text("who is elon musk", 0.47)

        self.assertEqual(cleaned, "who is elon musk")

    def test_scene_clarification_candidate_true_for_brightness_phrase(self):
        self.assertTrue(_is_scene_clarification_candidate("keep normal brightness"))

    def test_scene_clarification_candidate_false_for_general_chat(self):
        self.assertFalse(_is_scene_clarification_candidate("how are you"))

    def test_session_end_command_matches_farewell_phrase(self):
        self.assertTrue(_is_session_end_command("ok bye-bye"))

    def test_yes_parser_accepts_multi_word_confirmation(self):
        self.assertTrue(_is_simple_yes("yes stop"))

    def test_scene_clarification_maps_keep_normal_brightness(self):
        resolved = _resolve_scene_clarification_followup("keep normal brightness")
        self.assertIsInstance(resolved, dict)
        self.assertEqual(resolved.get("intent"), "set_scene")
        self.assertEqual(resolved.get("slots", {}).get("scene_key"), "balanced_default")

    def test_voice_high_confidence_skips_confirmation(self):
        wake = _FakeWakeWordManager(
            voice_available=True,
            heard=[("set alarm for 6 30", 0.8)],
        )
        stt = _FakeSTTManager()

        text, confidence = get_query_text(stt, wake)

        self.assertEqual(text, "set alarm for 6 30")
        self.assertGreaterEqual(confidence, 0.58)

    def test_voice_low_confidence_yes_confirms_original_text(self):
        wake = _FakeWakeWordManager(
            voice_available=True,
            heard=[("play calm music", 0.4)],
            confirmations=["yes"],
        )
        stt = _FakeSTTManager()

        text, confidence = get_query_text(stt, wake)

        self.assertEqual(text, "play calm music")
        self.assertGreaterEqual(confidence, 0.58)

    def test_voice_low_confidence_no_retries_capture(self):
        wake = _FakeWakeWordManager(
            voice_available=True,
            heard=[("set timer", 0.33), ("set timer for 20 minutes", 0.74)],
            confirmations=["no"],
        )
        stt = _FakeSTTManager()

        text, confidence = get_query_text(stt, wake)

        self.assertEqual(text, "set timer for 20 minutes")
        self.assertAlmostEqual(confidence, 0.74)

    @patch("builtins.input", side_effect=["audio:test.wav", "no", "set lights warm"])
    def test_audio_low_confidence_no_falls_back_to_typed_retry(self, _mock_input):
        wake = _FakeWakeWordManager(voice_available=False)
        stt = _FakeSTTManager(transcript="set lights", confidence=0.31)

        text, confidence = get_query_text(stt, wake)

        self.assertEqual(text, "set lights warm")
        self.assertEqual(confidence, 1.0)

    def test_wake_word_manager_accepts_hello(self):
        manager = WakeWordManager(mode="keyboard", wake_word="hey smart bed")
        self.assertTrue(manager.matches_wake_text("hello"))


if __name__ == "__main__":
    unittest.main()
