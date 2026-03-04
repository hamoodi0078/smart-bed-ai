import unittest
from datetime import datetime

from commands.lights import handle_light_intent, handle_light_intent_result
from commands.registry import match, register
from commands.reminders import handle_reminder_intent, handle_reminder_intent_result
from commands.sleep import handle_sleep_intent, handle_sleep_intent_result


class TestCommandRegistry(unittest.TestCase):
    def test_register_and_match_uses_alias_phrase(self):
        def _handler(text: str) -> str:
            return f"handled:{text}"

        register("registry_test_lights", _handler, aliases=("test lights",))
        matched = match("please set test lights now")

        self.assertIs(matched, _handler)


class TestExtractedCommandHandlers(unittest.TestCase):
    def test_light_result_returns_led_effects(self):
        result = handle_light_intent_result("set lights warm and dim")

        self.assertEqual(result.text, "Okay, I will set the lights to a dim warm scene.")
        led_effects = [effect for effect in result.effects if effect.kind == "led"]
        self.assertEqual(len(led_effects), 2)

        color_effect = next(effect for effect in led_effects if effect.payload.get("op") == "set_user_color")
        self.assertEqual(color_effect.payload.get("color"), "orange")

        brightness_effect = next(
            effect for effect in led_effects if effect.payload.get("op") == "set_user_brightness"
        )
        self.assertEqual(brightness_effect.payload.get("brightness"), 0.25)

    def test_sleep_result_returns_activate_scene_effect(self):
        result = handle_sleep_intent_result("go to sleep")

        self.assertEqual(result.text, "I have started sleep mode with a calm light scene.")
        store_effects = [effect for effect in result.effects if effect.kind == "store"]
        self.assertEqual(len(store_effects), 1)
        self.assertEqual(store_effects[0].payload.get("op"), "activate_sleep_scene")

    def test_reminder_result_returns_store_effects_without_runtime_dependencies(self):
        now = datetime(2026, 3, 5, 2, 0, 0)
        result = handle_reminder_intent_result(
            "Remind me to check my project at 9 pm",
            reminders_summary="",
            now_provider=lambda: now,
        )

        self.assertEqual(result.text, "Okay, I will remind you to check your project tonight at 9 pm.")
        store_effects = [effect for effect in result.effects if effect.kind == "store"]
        self.assertEqual(len(store_effects), 2)

        append_effect = next(effect for effect in store_effects if effect.payload.get("op") == "append_planned_reminder")
        reminder = append_effect.payload.get("reminder", {})
        self.assertEqual(reminder.get("task"), "check my project")
        self.assertEqual(reminder.get("time"), "9 pm")

        nudge_effect = next(effect for effect in store_effects if effect.payload.get("op") == "set_reminder_nudge_state")
        state = nudge_effect.payload.get("state", {})
        self.assertTrue(bool(state.get("active")))
        self.assertEqual(state.get("task"), "check my project")

    def test_light_handler_sets_color_and_brightness(self):
        calls = {"color": None, "brightness": None}

        def _set_color(color: str) -> None:
            calls["color"] = color

        def _set_brightness(level: float) -> None:
            calls["brightness"] = level

        reply = handle_light_intent(
            "set lights warm and dim",
            set_user_led_color=_set_color,
            set_user_brightness=_set_brightness,
            log=lambda _: None,
        )

        self.assertEqual(calls["color"], "orange")
        self.assertEqual(calls["brightness"], 0.25)
        self.assertEqual(reply, "Okay, I will set the lights to a dim warm scene.")

    def test_sleep_handler_calls_activate_scene(self):
        called = {"value": False}

        def _activate() -> str:
            called["value"] = True
            return "scene applied"

        reply = handle_sleep_intent("go to sleep", activate_sleep_scene=_activate, log=lambda _: None)

        self.assertTrue(called["value"])
        self.assertEqual(reply, "I have started sleep mode with a calm light scene.")

    def test_reminder_handler_stores_timed_task_and_arms_nudge(self):
        reminders: list[dict[str, object]] = []
        nudge_state: dict[str, object] = {
            "active": False,
            "task": "",
            "nudge_sent": False,
            "nudge_time": None,
        }

        now = datetime(2026, 3, 5, 2, 0, 0)
        reply = handle_reminder_intent(
            "Remind me to check my project at 9 pm",
            planned_reminders=reminders,
            reminder_nudge_state=nudge_state,
            format_planned_reminders=lambda: "",
            now_provider=lambda: now,
            log=lambda _: None,
        )

        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0].get("task"), "check my project")
        self.assertEqual(reminders[0].get("time"), "9 pm")
        self.assertTrue(bool(nudge_state.get("active")))
        self.assertEqual(nudge_state.get("task"), "check my project")
        self.assertEqual(reply, "Okay, I will remind you to check your project tonight at 9 pm.")


if __name__ == "__main__":
    unittest.main()
