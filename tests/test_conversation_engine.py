import unittest
from datetime import datetime
from unittest.mock import patch

from ai.conversation_engine import ConversationEngine


class _MockResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": "ok"}}]}


class TestConversationEngineTemporalGrounding(unittest.TestCase):
    @patch("ai.conversation_engine.requests.post")
    def test_temporal_grounding_message_is_injected(self, mock_post):
        mock_post.return_value = _MockResponse()
        engine = ConversationEngine(api_key="test-key")

        text = engine.generate_response("what is the current year?", personality="guide")

        self.assertEqual(text, "ok")
        self.assertTrue(mock_post.called)
        payload = mock_post.call_args.kwargs.get("json", {})
        messages = payload.get("messages", [])

        temporal_messages = [
            m.get("content", "")
            for m in messages
            if m.get("role") == "system"
            and "Temporal grounding requirement:" in m.get("content", "")
        ]

        self.assertEqual(len(temporal_messages), 1)
        temporal_msg = temporal_messages[0]
        self.assertIn("Current local year=", temporal_msg)
        self.assertIn(f"Current local year={datetime.now().year}", temporal_msg)


if __name__ == "__main__":
    unittest.main()
