import unittest

from main import wants_detailed_answer


class TestDetailTrigger(unittest.TestCase):
    def test_tell_me_about_triggers_detailed_mode(self):
        self.assertTrue(wants_detailed_answer("tell me about investing"))

    def test_walk_me_through_triggers_detailed_mode(self):
        self.assertTrue(wants_detailed_answer("walk me through index funds"))

    def test_short_chat_does_not_trigger_detailed_mode(self):
        self.assertFalse(wants_detailed_answer("okay"))


if __name__ == "__main__":
    unittest.main()
