import unittest

from main import _split_for_fast_tts_start, play_tts_with_fast_start


class _FakeTTS:
    def __init__(self):
        self.calls = []

    def synthesize_to_mp3(self, text, filename="latest_response.mp3", voice_override="", pace_override=1.0):
        self.calls.append(
            {
                "text": text,
                "filename": filename,
                "voice_override": voice_override,
                "pace_override": pace_override,
            }
        )
        return f"output_audio/{filename}"


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


class TestFastTTSStart(unittest.TestCase):
    def test_split_short_text_has_no_tail(self):
        head, tail = _split_for_fast_tts_start("Short response.")
        self.assertEqual(head, "Short response.")
        self.assertEqual(tail, "")

    def test_split_prefers_punctuation_for_head(self):
        text = "This is sentence one. This is sentence two with more detail and context."
        head, tail = _split_for_fast_tts_start(text, head_limit_chars=30)
        self.assertTrue(head.endswith("."))
        self.assertTrue(tail.startswith("This is"))

    def test_play_tts_with_fast_start_queues_tail_for_long_text(self):
        tts = _FakeTTS()
        player = _FakePlayer()
        text = (
            "This is a longer response that should be split for fast start and begin speaking immediately. "
            "The second part should be queued while the first part starts speaking so users feel less delay. "
            "This final sentence ensures the response is beyond the fast-start character threshold."
        )

        first_audio = play_tts_with_fast_start(tts, player, text, voice_override="nova", pace_override=1.1)

        self.assertEqual(first_audio, "output_audio/latest_response_head.mp3")
        self.assertEqual(len(tts.calls), 2)
        self.assertEqual(tts.calls[0]["filename"], "latest_response_head.mp3")
        self.assertEqual(tts.calls[1]["filename"], "latest_response_tail.mp3")
        self.assertEqual(len(player.played), 1)
        self.assertEqual(len(player.queued), 1)


if __name__ == "__main__":
    unittest.main()
