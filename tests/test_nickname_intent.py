import unittest

from main import (
    _detect_compound_control_intents,
    _resolve_followup_control_intent,
    build_wake_aliases_from_profile,
    build_wake_greeting,
    detect_natural_bed_intent,
)


class TestNicknameIntent(unittest.TestCase):
    def test_conversational_set_nickname_statement(self):
        intent, payload = detect_natural_bed_intent("jojo is your nick name")

        self.assertEqual(intent, "set_bed_nickname")
        self.assertEqual(payload.get("nickname"), "jojo")

    def test_conversational_set_nickname_call_you(self):
        intent, payload = detect_natural_bed_intent("jojo i would like to call you")

        self.assertEqual(intent, "set_bed_nickname")
        self.assertEqual(payload.get("nickname"), "jojo")

    def test_get_nickname_question(self):
        intent, _ = detect_natural_bed_intent("what is your nick name ?")

        self.assertEqual(intent, "get_bed_nickname")

    def test_nickname_setup_with_u_shorthand(self):
        intent, _ = detect_natural_bed_intent("i want to give u a nickname")

        self.assertEqual(intent, "nickname_setup")

    def test_natural_color_command_without_word_lights(self):
        intent, payload = detect_natural_bed_intent("make it red")

        self.assertEqual(intent, "set_color")
        self.assertEqual(payload.get("color"), "red")

    def test_natural_brightness_percentage_command(self):
        intent, payload = detect_natural_bed_intent("set lights to 35% brightness")

        self.assertEqual(intent, "brightness_set")
        self.assertEqual(payload.get("brightness_percent"), 35)

    def test_followup_light_command_uses_last_action_context(self):
        profile = {"runtime_flags": {"last_action": {"intent": "set_color"}}}

        intent, payload = _resolve_followup_control_intent("a bit dimmer", profile)

        self.assertEqual(intent, "brightness_down")
        self.assertEqual(payload, {})

    def test_followup_music_command_uses_last_action_context(self):
        profile = {"runtime_flags": {"last_action": {"intent": "play_music"}}}

        intent, payload = _resolve_followup_control_intent("pause it", profile)

        self.assertEqual(intent, "pause_music_followup")
        self.assertEqual(payload, {})

    def test_compound_intents_parse_color_then_brightness(self):
        profile = {"runtime_flags": {"last_action": {}}}

        steps = _detect_compound_control_intents(
            "make it red and set lights to 30% brightness", profile
        )

        intents = [s.get("intent") for s in steps]
        self.assertIn("set_color", intents)
        self.assertIn("brightness_set", intents)

    def test_compound_intents_parse_music_then_light_followup(self):
        profile = {"runtime_flags": {"last_action": {"intent": "set_color"}}}

        steps = _detect_compound_control_intents("play calm music and a bit dimmer", profile)

        intents = [s.get("intent") for s in steps]
        self.assertIn("play_music", intents)
        self.assertIn("brightness_down", intents)

    def test_wake_aliases_include_repeated_letter_variant(self):
        profile = {"preferences": {"bed_nickname": "ishfaaq", "wake_aliases": []}}

        aliases = build_wake_aliases_from_profile(profile)

        self.assertIn("ishfaaq", aliases)
        self.assertIn("ishfaq", aliases)
        self.assertIn("hey ishfaq", aliases)

    def test_wake_greeting_includes_user_name(self):
        profile = {"name": "amjad"}

        greeting = build_wake_greeting(profile)

        self.assertTrue(greeting.startswith("Good "))
        self.assertIn("amjad", greeting)
        self.assertIn("sleep mode", greeting)

    def test_wake_greeting_without_name_uses_generic_text(self):
        profile = {}

        greeting = build_wake_greeting(profile)

        self.assertTrue(greeting.startswith("Good "))
        self.assertIn("I am here and listening.", greeting)
        self.assertIn("sleep mode", greeting)

    def test_wake_greeting_uses_arabic_when_language_preference_is_arabic(self):
        profile = {"name": "أمجد", "preferences": {"language": "ar"}}

        greeting = build_wake_greeting(profile)

        self.assertIn("أمجد", greeting)
        self.assertIn("أنا هنا وجاهز للمساعدة", greeting)
        self.assertIn("sleep mode", greeting)


if __name__ == "__main__":
    unittest.main()
