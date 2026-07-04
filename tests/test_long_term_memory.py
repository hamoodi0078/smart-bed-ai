import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from ai.long_term_memory import LongTermMemoryStore


class TestLongTermMemoryStore(unittest.TestCase):
    def test_records_and_retrieves_relevant(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "memory.json"
            store = LongTermMemoryStore(path=str(path))
            store.record_turn(
                "I am stressed about my exam", "Let's make a plan.", "distressed", "therapist"
            )
            store.record_turn("I finished workout", "Great momentum.", "motivated", "coach")

            items = store.retrieve_relevant("exam stress plan", max_items=1)
            self.assertEqual(len(items), 1)
            self.assertIn("exam", items[0]["user"].lower())

    def test_memory_prompt_line(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "memory.json"
            store = LongTermMemoryStore(path=str(path))
            store.record_turn(
                "I keep waking up at 3am", "Use a wind-down routine.", "low_energy", "therapist"
            )

            line = store.memory_prompt_line("sleep issue")
            self.assertIn("Continuity memory", line)

    def test_infer_invisible_routine_detects_consistent_guide_window(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "memory.json"
            store = LongTermMemoryStore(path=str(path))
            store._save(
                {
                    "entries": [
                        {
                            "ts": "2026-02-19T21:04:00",
                            "user": "start guide session",
                            "assistant": "Sure",
                            "emotion": "neutral",
                            "personality": "guide",
                        },
                        {
                            "ts": "2026-02-20T21:05:00",
                            "user": "guide session now",
                            "assistant": "Sure",
                            "emotion": "neutral",
                            "personality": "guide",
                        },
                        {
                            "ts": "2026-02-21T21:06:00",
                            "user": "start guide",
                            "assistant": "Sure",
                            "emotion": "neutral",
                            "personality": "guide",
                        },
                    ]
                }
            )

            routine = store.infer_invisible_routine(now=datetime(2026, 2, 21, 21, 1), days=7)
            self.assertEqual(routine.get("pattern"), "guide_session")
            self.assertTrue(bool(routine.get("prep_window_active", False)))
            self.assertIn("guide", str(routine.get("offer_line", "")).lower())

    def test_inject_daily_events_updates_summary_and_latest_context(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "memory.json"
            store = LongTermMemoryStore(path=str(path))
            inserted = store.inject_daily_events(
                [
                    {
                        "title": "High-pressure school presentation",
                        "summary": "big audience",
                        "stress_level": "high",
                    }
                ],
                source="calendar",
            )

            self.assertEqual(inserted, 1)
            summary = store.latest_daily_events_summary(hours=48, max_items=2)
            self.assertIn("High-pressure school presentation", summary)
            self.assertIn("stress=high", summary)
            self.assertIn("source=calendar", summary)

            latest_context = store.latest_memory_context()
            self.assertIn("Daily events context", latest_context)


if __name__ == "__main__":
    unittest.main()
