import unittest

from ai.acoustic_echo_guard import AcousticEchoGuard


class TestAcousticEchoGuard(unittest.TestCase):
    def test_rejects_low_confidence_during_playback(self):
        guard = AcousticEchoGuard(min_confidence_when_playing=0.72)

        self.assertFalse(
            guard.should_accept_barge_in(playback_active=True, text="hello", confidence=0.4)
        )
        self.assertTrue(
            guard.should_accept_barge_in(playback_active=True, text="stop", confidence=0.9)
        )

    def test_accepts_when_not_playing(self):
        guard = AcousticEchoGuard(min_confidence_when_playing=0.9)
        self.assertTrue(
            guard.should_accept_barge_in(playback_active=False, text="yes", confidence=0.1)
        )


if __name__ == "__main__":
    unittest.main()
