import unittest

from ai.realtime_voice_pipeline import RealtimeVoicePipeline


class _FakeTTS:
    def __init__(self):
        self.calls = []

    def synthesize_to_mp3(self, text, filename="", voice_override="", pace_override=1.0):
        self.calls.append(text)
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
        full = pipeline.speak_from_text_stream(text)

        self.assertIn("Hello there.", tts.calls[0])
        self.assertTrue(any("How are you?" in c for c in tts.calls))
        self.assertEqual(full, "Hello there. How are you? I can help")


if __name__ == "__main__":
    unittest.main()
