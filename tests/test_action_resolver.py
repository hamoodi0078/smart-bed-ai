import unittest

from ai.action_resolver import resolve_action
from main import _execute_resolved_action


class _FakeLED:
    def __init__(self):
        self.animation = ""
        self.brightness = 0.0

    def set_user_animation(self, animation):
        self.animation = animation

    def set_user_brightness(self, value):
        self.brightness = float(value)


class _FakeSpotify:
    def play_track_query(self, query):
        return True, f"Spotify playing: {query or 'default'}"

    def pause(self):
        return True, "Spotify paused"


class _FakeLocalMusic:
    def play_query(self, query):
        return True, f"Local playing: {query}"

    def pause(self):
        return True, "Local paused"


class _FakeEnvironmentOrchestrator:
    def apply_scene(self, led, profile, scene):
        profile.setdefault("environment", {})["last_scene_key"] = scene.get("key", "")
        return scene.get("line", "Environment scene applied.")


class _FakeSleepEngine:
    def build_wind_down_autopilot(self, profile, minutes=45):
        profile.setdefault("sleep", {})["wind_down_enabled"] = True
        profile["sleep"]["wind_down_minutes"] = int(minutes)
        return f"Wind-down autopilot enabled for {minutes} minute(s)."

    def disable_wind_down_autopilot(self, profile):
        profile.setdefault("sleep", {})["wind_down_enabled"] = False
        return "Wind-down autopilot disabled."


class _FakeSleepRoutine:
    def start_sleep_timer(self, minutes, _callback):
        return f"Sleep timer started for {minutes} min"


class _FakeRoutineEngine:
    def parse_minutes_from_text(self, text, default_minutes=45):
        try:
            return int(str(text).strip())
        except Exception:
            return int(default_minutes)


class TestActionResolver(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "preferences": {"response_style": "balanced", "thinking_ack_mode": "minimal"},
            "runtime_flags": {},
        }

    def test_free_form_coverage_has_25_plus_phrasings(self):
        expected = [
            ("I'm tired, make everything calmer and help me sleep now", "start_wind_down"),
            ("Can you make lights softer and play low ambient music?", "start_wind_down"),
            ("Don't talk much tonight, just keep it simple", "set_response_style"),
            ("undo that", "undo_last_action"),
            ("revert last action", "undo_last_action"),
            ("start wind down now", "start_wind_down"),
            ("help me sleep now", "start_wind_down"),
            ("optimize sleep now", "start_wind_down"),
            ("lights softer", "set_scene"),
            ("dim the lights", "set_scene"),
            ("warm calm lights please", "set_scene"),
            ("play ambient", "play_music"),
            ("start calm music", "play_music"),
            ("pause music", "pause_music"),
            ("stop music now", "pause_music"),
            ("short replies tonight", "set_response_style"),
            ("quiet replies", "set_response_style"),
            ("talk more in detail", "set_response_style"),
            ("شرح بالتفصيل", "set_response_style"),
            ("انا تعبان ونوم", "start_wind_down"),
            ("خفف الاضاءة", "set_scene"),
            ("شغل موسيقى هادئة", "play_music"),
            ("وقف الموسيقى", "pause_music"),
            ("تكلم قليل", "set_response_style"),
            ("help sleep", "start_wind_down"),
        ]

        matched = 0
        for phrase, intent in expected:
            resolved = resolve_action(phrase, self.profile, context={})
            if resolved.get("intent") == intent:
                matched += 1

        self.assertGreaterEqual(len(expected), 25)
        self.assertEqual(matched, len(expected))

    def test_confidence_routing_bands(self):
        high = resolve_action("start wind down now", self.profile, context={})
        medium = resolve_action("lights", self.profile, context={})
        low = resolve_action("tell me something interesting", self.profile, context={})

        self.assertGreaterEqual(float(high.get("confidence", 0.0)), 0.78)
        self.assertTrue(0.45 <= float(medium.get("confidence", 0.0)) < 0.78)
        self.assertTrue(str(medium.get("clarify_question", "")).strip())
        self.assertLess(float(low.get("confidence", 0.0)), 0.45)

    def test_undo_revert_behavior(self):
        led = _FakeLED()
        spotify = _FakeSpotify()
        local_music = _FakeLocalMusic()
        sleep_engine = _FakeSleepEngine()
        orchestrator = _FakeEnvironmentOrchestrator()
        sleep_routine = _FakeSleepRoutine()
        routine_engine = _FakeRoutineEngine()

        msg_set, handled_set = _execute_resolved_action(
            {
                "intent": "set_response_style",
                "slots": {"response_style": "quick", "thinking_ack_mode": "off"},
            },
            self.profile,
            led,
            spotify,
            local_music,
            sleep_engine,
            orchestrator,
            sleep_routine,
            routine_engine,
            lambda: None,
        )
        self.assertTrue(handled_set)
        self.assertIn("Done", msg_set)
        self.assertEqual(self.profile["preferences"]["response_style"], "quick")

        msg_undo, handled_undo = _execute_resolved_action(
            {"intent": "undo_last_action", "slots": {}},
            self.profile,
            led,
            spotify,
            local_music,
            sleep_engine,
            orchestrator,
            sleep_routine,
            routine_engine,
            lambda: None,
        )
        self.assertTrue(handled_undo)
        self.assertIn("reverted", msg_undo)
        self.assertEqual(self.profile["preferences"]["response_style"], "balanced")
        self.assertEqual(self.profile["preferences"]["thinking_ack_mode"], "minimal")


if __name__ == "__main__":
    unittest.main()
