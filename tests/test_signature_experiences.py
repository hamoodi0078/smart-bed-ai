import unittest

from ai.signature_experiences import SignatureExperienceEngine


class _FakeSleepEngine:
    def stress_decompression_protocol(self, profile, minutes=5):
        profile.setdefault("sleep", {})["last_decompression_minutes"] = minutes
        return f"Stress decompression ({minutes} min)."

    def partner_conflict_safe_routine(self, _profile):
        return "Conflict-safe routine ready."

    def adaptive_wake_routine_plan(self, _profile):
        return "Adaptive wake plan ready."


class _FakeEnvironmentOrchestrator:
    def signature_scene(self, mode):
        return {
            "key": f"sig_{mode}",
            "animation": "breathing",
            "color": "warmwhite",
            "brightness": 0.2,
            "line": f"Environment scene: {mode}.",
        }

    def apply_scene(self, _led, _profile, scene):
        return scene.get("line", "Environment scene applied.")


class _FakeLED:
    pass


class _FakeSpotify:
    def play_track_query(self, query):
        return True, f"Spotify playing: {query}"


class _FakeLocalMusic:
    def play_query(self, query):
        return True, f"Local playing: {query}"


class TestSignatureExperiences(unittest.TestCase):
    def setUp(self):
        self.engine = SignatureExperienceEngine()
        self.profile = {}
        self.sleep_engine = _FakeSleepEngine()
        self.env = _FakeEnvironmentOrchestrator()
        self.led = _FakeLED()
        self.spotify = _FakeSpotify()
        self.local_music = _FakeLocalMusic()

    def test_phrase_variants_cover_each_mode(self):
        cases = {
            "dana_deep_recovery": [
                "start deep recovery",
                "i need deep reset tonight",
                "run dana deep recovery",
            ],
            "couple_harmony_wake": [
                "run couple harmony wake",
                "start partner harmony mode",
                "start couple harmony wake",
            ],
            "ninety_second_reset": [
                "90 second reset",
                "90-second reset",
                "reset me now",
            ],
        }

        for expected_mode, phrases in cases.items():
            for phrase in phrases:
                self.assertEqual(self.engine.detect_experience(phrase), expected_mode)

    def test_deep_recovery_run_returns_premium_confirmation(self):
        message, handled = self.engine.run(
            "start deep recovery",
            self.profile,
            self.sleep_engine,
            self.env,
            self.led,
            self.spotify,
            self.local_music,
        )
        self.assertTrue(handled)
        self.assertIn("Dana Deep Recovery", message)
        self.assertIn("Environment scene", message)
        self.assertIn("Stress decompression", message)

    def test_couple_harmony_run_returns_bundle(self):
        message, handled = self.engine.run(
            "run couple harmony wake",
            self.profile,
            self.sleep_engine,
            self.env,
            self.led,
            self.spotify,
            self.local_music,
        )
        self.assertTrue(handled)
        self.assertIn("Couple Harmony Wake", message)
        self.assertIn("Conflict-safe routine", message)
        self.assertIn("Adaptive wake", message)

    def test_ninety_second_reset_run_returns_bundle(self):
        message, handled = self.engine.run(
            "reset me now",
            self.profile,
            self.sleep_engine,
            self.env,
            self.led,
            self.spotify,
            self.local_music,
        )
        self.assertTrue(handled)
        self.assertIn("90-Second Reset", message)
        self.assertIn("Fast support mode", message)


if __name__ == "__main__":
    unittest.main()
