import unittest

from ai.intent_classifier import detect_personality_switch


class TestPersonalitySwitchIntent(unittest.TestCase):
    def test_switch_command_detected(self):
        self.assertEqual(detect_personality_switch("switch to guide mode"), "guide")

    def test_set_command_detected(self):
        self.assertEqual(detect_personality_switch("set personality to therapist"), "therapist")

    def test_question_with_mode_not_detected(self):
        self.assertIsNone(detect_personality_switch("how can the guide mode help in daily life?"))


if __name__ == "__main__":
    unittest.main()
