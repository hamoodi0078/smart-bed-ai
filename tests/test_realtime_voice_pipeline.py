import unittest

from ai.realtime_voice_pipeline import RealtimeVoicePipeline


class _FakeTTS:
    def __init__(self):
        self.calls = []

    def synthesize_to_mp3(
        self,
        text,
        filename="",
        voice_override="",
        pace_override=1.0,
        emotion_state="neutral",
        profile_override="",
    ):
        self.calls.append(
            {
                "text": text,
                "emotion_state": emotion_state,
                "profile_override": profile_override,
            }
        )
        return f"fake/{filename or 'audio'}.mp3"


class _FakePlayer:
    def __init__(self):
        self.played = []
        self.queued = []
        self._playing = False

    def play_file(self, path):
        self.played.append(path)
        self._playing = True
        return True

    def queue_file(self, path):
        self.queued.append(path)
        return True

    def is_playing(self):
        return self._playing


class TestRealtimeVoicePipeline(unittest.TestCase):
    def test_sentence_chunks_are_streamed_to_tts(self):
        tts = _FakeTTS()
        player = _FakePlayer()
        pipeline = RealtimeVoicePipeline(tts, player)

        text = ["Hello there. ", "How are you?", " I can help"]
        full = pipeline.speak_from_text_stream(text, emotion_state="distressed", profile_override="whisper")

        self.assertIn("Hello there.", tts.calls[0]["text"])
        self.assertTrue(any("How are you?" in c["text"] for c in tts.calls))
        self.assertTrue(all(c["emotion_state"] == "distressed" for c in tts.calls))
        self.assertTrue(all(c["profile_override"] == "whisper" for c in tts.calls))
        self.assertEqual(full, "Hello there. How are you? I can help")

    def test_preload_callback_fires_once_for_sleep_phase(self):
        tts = _FakeTTS()
        player = _FakePlayer()
        pipeline = RealtimeVoicePipeline(tts, player)

        phases = []
        text = ["Tonight we will start a sleep routine. ", "I will guide you slowly."]
        full = pipeline.speak_from_text_stream(text, on_preload_start=lambda p: phases.append(p))

        self.assertEqual(full, "Tonight we will start a sleep routine. I will guide you slowly.")
        self.assertEqual(phases, ["sleep"])


if __name__ == "__main__":
    unittest.main()
