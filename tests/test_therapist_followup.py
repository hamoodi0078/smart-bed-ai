from datetime import datetime
import unittest

from main import (
    get_due_therapist_followup,
    normalize_followup_tone,
    record_therapist_concern,
    resolve_therapist_followup_if_answered,
)


class TestTherapistFollowup(unittest.TestCase):
    def test_record_concern_creates_next_day_pending_entry(self):
        profile = {"daily_life": {}}

        created = record_therapist_concern(
            profile,
            user_text="I feel very worried about my exams tonight",
            personality="therapist",
            now=datetime(2026, 2, 20, 23, 15, 0),
        )

        self.assertTrue(created)
        entries = profile["daily_life"]["emotional_followups"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["followup_due_date"], "2026-02-21")
        self.assertFalse(entries[0]["resolved"])

    def test_due_followup_triggers_next_day_once(self):
        profile = {"daily_life": {}}
        record_therapist_concern(
            profile,
            user_text="I am anxious about tomorrow",
            personality="therapist",
            now=datetime(2026, 2, 20, 22, 0, 0),
        )

        prompt = get_due_therapist_followup(
            profile,
            personality="therapist",
            user_text="good morning",
            now=datetime(2026, 2, 21, 9, 0, 0),
        )
        self.assertIn("yesterday", prompt.lower())

        second_prompt = get_due_therapist_followup(
            profile,
            personality="therapist",
            user_text="how are you",
            now=datetime(2026, 2, 21, 10, 0, 0),
        )
        self.assertEqual(second_prompt, "")

    def test_followup_can_resolve_and_opt_out(self):
        profile = {"daily_life": {}}
        record_therapist_concern(
            profile,
            user_text="I am stressed",
            personality="therapist",
            now=datetime(2026, 2, 20, 22, 0, 0),
        )
        get_due_therapist_followup(
            profile,
            personality="therapist",
            user_text="morning",
            now=datetime(2026, 2, 21, 8, 0, 0),
        )

        resolved = resolve_therapist_followup_if_answered(
            profile,
            user_text="Please do not ask about this again",
            now=datetime(2026, 2, 21, 8, 1, 0),
        )

        self.assertTrue(resolved)
        self.assertTrue(profile["daily_life"]["followup_opt_out"])

    def test_followup_tone_normalization(self):
        self.assertEqual(normalize_followup_tone("teen-friendly"), "teen")
        self.assertEqual(normalize_followup_tone("islamic supportive"), "islamic")
        self.assertEqual(normalize_followup_tone("unknown"), "soft")

    def test_islamic_followup_tone_changes_prompt_wording(self):
        profile = {
            "daily_life": {},
            "preferences": {"therapist_followup_tone": "islamic supportive"},
        }
        record_therapist_concern(
            profile,
            user_text="I feel worried about my future",
            personality="therapist",
            now=datetime(2026, 2, 20, 22, 0, 0),
        )

        prompt = get_due_therapist_followup(
            profile,
            personality="therapist",
            user_text="good morning",
            now=datetime(2026, 2, 21, 9, 0, 0),
        )
        self.assertTrue(
            ("allah" in prompt.lower())
            or ("alhamdulillah" in prompt.lower())
            or ("pray" in prompt.lower())
        )


if __name__ == "__main__":
    unittest.main()
