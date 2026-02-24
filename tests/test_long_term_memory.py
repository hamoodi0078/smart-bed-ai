import tempfile
import unittest
from pathlib import Path

from ai.long_term_memory import LongTermMemoryStore


class TestLongTermMemoryStore(unittest.TestCase):
    def test_records_and_retrieves_relevant(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "memory.json"
            store = LongTermMemoryStore(path=str(path))
            store.record_turn("I am stressed about my exam", "Let's make a plan.", "distressed", "therapist")
            store.record_turn("I finished workout", "Great momentum.", "motivated", "coach")

            items = store.retrieve_relevant("exam stress plan", max_items=1)
            self.assertEqual(len(items), 1)
            self.assertIn("exam", items[0]["user"].lower())

    def test_memory_prompt_line(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "memory.json"
            store = LongTermMemoryStore(path=str(path))
            store.record_turn("I keep waking up at 3am", "Use a wind-down routine.", "low_energy", "therapist")

            line = store.memory_prompt_line("sleep issue")
            self.assertIn("Continuity memory", line)


if __name__ == "__main__":
    unittest.main()
