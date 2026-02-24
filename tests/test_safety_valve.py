import unittest

from ai.safety_valve import SafetyValve


class TestSafetyValve(unittest.TestCase):
    def test_escalates_to_therapist_after_distress_streak(self):
        valve = SafetyValve(distress_turn_threshold=3)
        profile = {}

        p1, _ = valve.apply(profile, base_personality="coach", emotion_state="distressed")
        p2, _ = valve.apply(profile, base_personality="coach", emotion_state="distressed")
        p3, reason = valve.apply(profile, base_personality="coach", emotion_state="distressed")

        self.assertEqual(p1, "coach")
        self.assertEqual(p2, "coach")
        self.assertEqual(p3, "therapist")
        self.assertEqual(reason, "safety_valve_distress_escalation")

    def test_decay_when_not_distressed(self):
        valve = SafetyValve(distress_turn_threshold=3)
        profile = {}
        valve.apply(profile, base_personality="coach", emotion_state="distressed")
        valve.apply(profile, base_personality="coach", emotion_state="distressed")
        valve.apply(profile, base_personality="coach", emotion_state="neutral")

        self.assertEqual(profile["safety_valve"]["distress_streak"], 1)


if __name__ == "__main__":
    unittest.main()
