import unittest
from datetime import datetime

from ai.sleep_intelligence import SleepIntelligenceEngine


class TestPartnerModeAndRecoveryCard(unittest.TestCase):
    def setUp(self):
        self.engine = SleepIntelligenceEngine()

    def test_partner_mode_enable_and_status(self):
        profile = {"sleep": {}}

        enable_msg = self.engine.set_partner_mode_enabled(profile, enabled=True)
        status = self.engine.partner_mode_status(profile)

        self.assertIn("enabled", enable_msg.lower())
        self.assertIn("Partner Sleep Mode is on", status)

    def test_set_partner_profile_and_conflict_safe_routine(self):
        profile = {"sleep": {}}

        self.engine.set_partner_profile(profile, slot=0, name="Ali", wake_style="gentle")
        self.engine.set_partner_profile(profile, slot=1, name="Sara", wake_style="energizing")
        routine = self.engine.partner_conflict_safe_routine(profile)

        self.assertIn("Ali", routine)
        self.assertIn("Sara", routine)
        self.assertIn("staged wake", routine)

    def test_weekly_recovery_score_card_returns_trend_trigger_and_plan(self):
        profile = {
            "preferences": {"sleep_target_hours": 8.0},
            "sleep": {
                "bedtime_history": [
                    "2026-02-14T23:50:00",
                    "2026-02-15T00:40:00",
                    "2026-02-16T01:20:00",
                    "2026-02-17T00:50:00",
                    "2026-02-18T01:30:00",
                ],
                "wake_history": [
                    "2026-02-15T06:10:00",
                    "2026-02-16T06:30:00",
                    "2026-02-17T06:20:00",
                    "2026-02-18T06:30:00",
                    "2026-02-19T06:45:00",
                ],
                "night_wake_count": 2,
            },
        }

        card = self.engine.weekly_recovery_score_card(profile)

        self.assertIn("Recovery score card (weekly)", card)
        self.assertIn("Trend:", card)
        self.assertIn("Best night:", card)
        self.assertIn("Worst trigger:", card)
        self.assertIn("Next week plan:", card)

    def test_should_send_weekly_recovery_score_card_respects_weekly_guard(self):
        profile = {
            "sleep": {
                "bedtime_history": [
                    "2026-02-14T23:40:00",
                    "2026-02-15T23:50:00",
                    "2026-02-16T23:35:00",
                    "2026-02-17T23:45:00",
                ],
                "wake_history": [
                    "2026-02-15T06:20:00",
                    "2026-02-16T06:35:00",
                    "2026-02-17T06:15:00",
                    "2026-02-18T06:30:00",
                ],
            }
        }
        now = datetime(2026, 2, 21, 20, 0, 0)

        self.assertTrue(self.engine.should_send_weekly_recovery_score_card(profile, now=now))
        self.engine.mark_weekly_recovery_score_card_sent(profile, now=now)
        self.assertFalse(self.engine.should_send_weekly_recovery_score_card(profile, now=now))

        next_week = datetime(2026, 2, 28, 20, 0, 0)
        self.assertTrue(self.engine.should_send_weekly_recovery_score_card(profile, now=next_week))

    def test_should_not_send_weekly_recovery_score_card_outside_evening_or_with_low_data(self):
        low_data_profile = {
            "sleep": {
                "bedtime_history": [
                    "2026-02-14T23:40:00",
                    "2026-02-15T23:50:00",
                    "2026-02-16T23:35:00",
                ],
                "wake_history": [
                    "2026-02-15T06:20:00",
                    "2026-02-16T06:35:00",
                    "2026-02-17T06:15:00",
                ],
            }
        }
        morning = datetime(2026, 2, 21, 10, 0, 0)
        evening = datetime(2026, 2, 21, 20, 0, 0)

        self.assertFalse(
            self.engine.should_send_weekly_recovery_score_card(low_data_profile, now=evening)
        )

        enough_data_profile = {
            "sleep": {
                "bedtime_history": [
                    "2026-02-14T23:40:00",
                    "2026-02-15T23:50:00",
                    "2026-02-16T23:35:00",
                    "2026-02-17T23:45:00",
                ],
                "wake_history": [
                    "2026-02-15T06:20:00",
                    "2026-02-16T06:35:00",
                    "2026-02-17T06:15:00",
                    "2026-02-18T06:30:00",
                ],
            }
        }
        self.assertFalse(
            self.engine.should_send_weekly_recovery_score_card(enough_data_profile, now=morning)
        )


if __name__ == "__main__":
    unittest.main()
