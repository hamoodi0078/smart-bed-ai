import unittest

from ai.conversational_fillers import ConversationalFillerManager


class TestConversationalFillers(unittest.TestCase):
    def test_trigger_and_pick(self):
        manager = ConversationalFillerManager(trigger_after_seconds=0.5, cooldown_seconds=10.0)
        self.assertFalse(manager.should_play(0.2))
        self.assertTrue(manager.should_play(0.7))

        picked = manager.pick()
        self.assertTrue(bool(picked.strip()))


if __name__ == "__main__":
    unittest.main()
