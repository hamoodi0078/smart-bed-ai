import unittest

from ai.intent_classifier import detect_implicit_intent, detect_personality_switch


class TestPersonalitySwitchIntent(unittest.TestCase):
    def test_switch_command_detected(self):
        self.assertEqual(detect_personality_switch("switch to guide mode"), "guide")

    def test_set_command_detected(self):
        self.assertEqual(detect_personality_switch("set personality to therapist"), "therapist")

    def test_question_with_mode_not_detected(self):
        self.assertIsNone(detect_personality_switch("how can the guide mode help in daily life?"))


class TestImplicitIntent(unittest.TestCase):
    def test_brightness_complaint_maps_to_scene(self):
        resolved = detect_implicit_intent("It's getting a bit bright")
        self.assertEqual(resolved.get("intent"), "set_scene")
        self.assertIn("evening routine", str(resolved.get("partner_line", "")).lower())

    def test_quiet_room_maps_to_ambient_music(self):
        resolved = detect_implicit_intent("This room feels silent")
        self.assertEqual(resolved.get("intent"), "play_music")
        self.assertEqual(resolved.get("slots", {}).get("query"), "ambient")


if __name__ == "__main__":
    unittest.main()
