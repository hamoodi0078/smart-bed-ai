import re
import unittest
from datetime import datetime

from ai.sleep_intelligence import SleepIntelligenceEngine
from main import build_sleep_help


class TestSleepQualityScore(unittest.TestCase):
    def setUp(self):
        self.engine = SleepIntelligenceEngine()

    def test_sleep_quality_score_collecting_data_when_logs_are_insufficient(self):
        profile = {"preferences": {"sleep_target_hours": 8.0}, "sleep": {"bedtime_history": [], "wake_history": []}}

        answer = self.engine.sleep_quality_score(profile)

        self.assertIn("Sleep quality score: collecting data", answer)

    def test_sleep_quality_score_returns_numeric_score_with_why_line(self):
        profile = {
            "preferences": {"sleep_target_hours": 8.0},
            "sleep": {
                "bedtime_history": [
                    "2026-02-14T23:10:00",
                    "2026-02-15T23:45:00",
                    "2026-02-16T00:20:00",
                    "2026-02-17T23:30:00",
                ],
                "wake_history": [
                    "2026-02-15T06:40:00",
                    "2026-02-16T06:50:00",
                    "2026-02-17T06:40:00",
                    "2026-02-18T07:00:00",
                ],
                "night_wake_count": 2,
            },
        }

        answer = self.engine.sleep_quality_score(profile)

        self.assertRegex(answer, r"Sleep quality score: \d{1,3}/100")
        self.assertIn("Why:", answer)
        self.assertTrue(
            ("average sleep is" in answer)
            or ("bedtime shift is" in answer)
            or ("night wakes logged" in answer)
            or ("estimated sleep debt" in answer)
        )

    def test_sleep_help_mentions_sleep_quality_score_command(self):
        help_text = build_sleep_help()
        self.assertIn("sleep quality score", help_text)

    def test_bedtime_drift_alert_collecting_data_when_not_enough_logs(self):
        profile = {"sleep": {"bedtime_history": ["2026-02-14T23:00:00", "2026-02-15T23:10:00"]}}

        answer = self.engine.bedtime_drift_alert(profile)

        self.assertIn("Predictive bedtime drift: collecting data", answer)

    def test_bedtime_drift_alert_detects_late_drift_and_suggests_earlier_wind_down(self):
        profile = {
            "sleep": {
                "bedtime_history": [
                    "2026-02-14T22:00:00",
                    "2026-02-15T23:05:00",
                    "2026-02-16T00:15:00",
                    "2026-02-17T01:30:00",
                    "2026-02-18T02:40:00",
                ]
            }
        }

        answer = self.engine.bedtime_drift_alert(profile)

        self.assertTrue(answer.startswith("Predictive alert:"))
        self.assertIn("Start wind-down", answer)

    def test_should_send_bedtime_drift_alert_respects_daily_guard(self):
        profile = {
            "sleep": {
                "bedtime_history": [
                    "2026-02-14T22:00:00",
                    "2026-02-15T23:05:00",
                    "2026-02-16T00:15:00",
                    "2026-02-17T01:30:00",
                    "2026-02-18T02:40:00",
                ]
            }
        }
        now = datetime(2026, 2, 21, 20, 0, 0)

        self.assertTrue(self.engine.should_send_bedtime_drift_alert(profile, now=now))
        self.engine.mark_bedtime_drift_alert_sent(profile, now=now)
        self.assertFalse(self.engine.should_send_bedtime_drift_alert(profile, now=now))


if __name__ == "__main__":
    unittest.main()
