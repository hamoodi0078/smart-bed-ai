import unittest
from unittest.mock import patch

from ai.wake_word_manager import WakeWordManager
from main import (
    _is_llm_fallback_response,
    _is_scene_clarification_candidate,
    _is_session_end_command,
    _is_simple_yes,
    _is_wake_only_utterance,
    _looks_like_echo_capture,
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


class _FakeStreamingSTTManager:
    def __init__(self):
        self.calls = []

    def transcribe_microphone_with_interim(
        self,
        mic_device_index=None,
        timeout_seconds=5,
        max_phrase_seconds=16.0,
        silence_end_seconds=0.8,
        interim_callback=None,
    ):
        _ = (timeout_seconds, max_phrase_seconds, silence_end_seconds, interim_callback)
        self.calls.append(mic_device_index)
        if mic_device_index is None:
            return "how are you today", 0.91
        return "", 0.0


class _FakeVoiceWakeWordManager(_FakeWakeWordManager):
    def __init__(self, mic_index=1):
        super().__init__(voice_available=True)
        self.voice_timeout_seconds = 5
        self._mic_index = mic_index

    def get_voice_phrase_limit_seconds(self):
        return 0

    def get_active_mic_index(self):
        return self._mic_index


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

    def test_strict_stream_retries_default_microphone_when_index_fails(self):
        wake = _FakeVoiceWakeWordManager(mic_index=1)
        stt = _FakeStreamingSTTManager()

        text, confidence = get_query_text(stt, wake, require_api_stream=True)

        self.assertEqual(text, "how are you today")
        self.assertAlmostEqual(confidence, 0.91)
        self.assertEqual(stt.calls, [1, None])

    def test_voice_low_confidence_returns_empty_for_retry(self):
        wake = _FakeWakeWordManager(
            voice_available=True,
            heard=[("play calm music", 0.4)],
        )
        stt = _FakeSTTManager()

        text, confidence = get_query_text(stt, wake)

        self.assertEqual(text, "")
        self.assertEqual(confidence, 0.0)

    def test_voice_low_confidence_no_longer_uses_confirmation_retry(self):
        wake = _FakeWakeWordManager(
            voice_available=True,
            heard=[("set timer", 0.33), ("set timer for 20 minutes", 0.74)],
        )
        stt = _FakeSTTManager()

        text, confidence = get_query_text(stt, wake)

        self.assertEqual(text, "")
        self.assertEqual(confidence, 0.0)

    @patch("builtins.input", side_effect=["audio:test.wav"])
    def test_audio_low_confidence_returns_empty_for_retry(self, _mock_input):
        wake = _FakeWakeWordManager(voice_available=False)
        stt = _FakeSTTManager(transcript="set lights", confidence=0.31)

        text, confidence = get_query_text(stt, wake)

        self.assertEqual(text, "")
        self.assertEqual(confidence, 0.0)

    def test_wake_word_manager_accepts_hello(self):
        manager = WakeWordManager(mode="keyboard", wake_word="hey smart bed")
        self.assertTrue(manager.matches_wake_text("hello"))

    def test_wake_only_utterance_filter_accepts_pure_wake_phrase(self):
        manager = WakeWordManager(
            mode="keyboard",
            wake_word="hey smart bed",
            wake_aliases=["hello smart bed"],
        )
        self.assertTrue(_is_wake_only_utterance(manager, "hey smart bed please"))
        self.assertTrue(_is_wake_only_utterance(manager, "hello smart bed"))

    def test_wake_only_utterance_filter_rejects_real_command(self):
        manager = WakeWordManager(mode="keyboard", wake_word="hey smart bed")
        self.assertFalse(_is_wake_only_utterance(manager, "hey smart bed turn on blue light"))

    def test_echo_capture_detector_flags_replayed_assistant_phrase(self):
        user_text = "getting cozy can really help you relax"
        last_assistant = "Getting cozy can really help you relax. Do you want me to start wind-down now with dim lights and calm audio?"
        self.assertTrue(_looks_like_echo_capture(user_text, last_assistant, confidence=0.62))

    def test_echo_capture_detector_ignores_valid_new_query(self):
        user_text = "how are you today"
        last_assistant = "Do you want me to start wind-down now with dim lights and calm audio?"
        self.assertFalse(_looks_like_echo_capture(user_text, last_assistant, confidence=0.93))

    def test_llm_fallback_detector_supports_deepgram_prefix(self):
        self.assertTrue(
            _is_llm_fallback_response(
                "(Deepgram fallback - guide) I heard: 'hello'. I can respond better once Deepgram Voice Agent access is available."
            )
        )
        self.assertTrue(_is_llm_fallback_response("(Offline fallback - guide) legacy"))
        self.assertFalse(_is_llm_fallback_response("Normal response"))


if __name__ == "__main__":
    unittest.main()
