import unittest
from datetime import datetime

from ai.proactive_automation_engine import ProactiveAutomationEngine


class TestProactiveAutomation(unittest.TestCase):
    def setUp(self):
        self.engine = ProactiveAutomationEngine()
        self.profile = {
            "preferences": {"quiet_window": "", "adaptive_wake_enabled": True},
            "sleep": {
                "bedtime_history": [
                    "2026-02-14T22:00:00",
                    "2026-02-15T23:05:00",
                    "2026-02-16T00:15:00",
                    "2026-02-17T01:30:00",
                ],
                "night_wake_count": 1,
            },
        }

    def test_quiet_window_suppresses_all_suggestions(self):
        self.profile["preferences"]["quiet_window"] = "23:00-07:00"
        now = datetime(2026, 2, 22, 23, 30, 0)
        suggestions = self.engine.evaluate(
            self.profile,
            now=now,
            session_state={"interrupt_count_today": 0, "active_goals_count": 1, "bedtime_drift_alert": "Predictive alert: drift"},
        )
        self.assertEqual(suggestions, [])

    def test_dedup_same_day_and_window(self):
        now = datetime(2026, 2, 22, 20, 0, 0)
        session_state = {"interrupt_count_today": 0, "active_goals_count": 1, "bedtime_drift_alert": "Predictive alert: drift"}

        first = self.engine.evaluate(self.profile, now=now, session_state=session_state)
        self.assertTrue(any(s.get("key") == "bedtime_drift_intervention" for s in first))

        drift = [s for s in first if s.get("key") == "bedtime_drift_intervention"][0]
        self.engine.mark_executed(self.profile, drift, now=now)

        second = self.engine.evaluate(self.profile, now=now, session_state=session_state)
        self.assertFalse(any(s.get("key") == "bedtime_drift_intervention" for s in second))

    def test_interrupt_threshold_reduces_to_overload_prompt(self):
        now = datetime(2026, 2, 22, 21, 0, 0)
        suggestions = self.engine.evaluate(
            self.profile,
            now=now,
            session_state={"interrupt_count_today": 5, "active_goals_count": 1, "bedtime_drift_alert": ""},
        )
        keys = {s.get("key") for s in suggestions}
        self.assertIn("overload_simplification_prompt", keys)

    def test_adaptive_morning_ramp_trigger(self):
        now = datetime(2026, 2, 22, 8, 0, 0)
        suggestions = self.engine.evaluate(
            self.profile,
            now=now,
            session_state={"interrupt_count_today": 0, "active_goals_count": 1, "bedtime_drift_alert": ""},
        )
        keys = {s.get("key") for s in suggestions}
        self.assertIn("adaptive_morning_ramp", keys)

    def test_night_wake_rescue_trigger(self):
        now = datetime(2026, 2, 22, 2, 30, 0)
        suggestions = self.engine.evaluate(
            self.profile,
            now=now,
            session_state={"interrupt_count_today": 0, "active_goals_count": 1, "bedtime_drift_alert": ""},
        )
        keys = {s.get("key") for s in suggestions}
        self.assertIn("night_wake_rescue", keys)

    def test_goal_overload_simplification_trigger(self):
        now = datetime(2026, 2, 22, 19, 0, 0)
        suggestions = self.engine.evaluate(
            self.profile,
            now=now,
            session_state={"interrupt_count_today": 1, "active_goals_count": 4, "bedtime_drift_alert": ""},
        )
        keys = {s.get("key") for s in suggestions}
        self.assertIn("goal_overload_simplification", keys)


if __name__ == "__main__":
    unittest.main()
