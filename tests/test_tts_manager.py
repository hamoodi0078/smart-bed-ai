import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ai.tts_manager import TTSManager


class TestTTSManager(unittest.TestCase):
    def test_normalize_tts_text_collapses_spaces_and_tightens_punctuation(self):
        manager = TTSManager(api_key="key")

        normalized = manager._normalize_tts_text(" Hello   world  ,  how are   you ? ")

        self.assertEqual(normalized, "Hello world, how are you?")

    def test_cache_path_is_stable_for_equivalent_text(self):
        manager = TTSManager(api_key="key")

        p1 = manager._cache_path_for(manager._normalize_tts_text("Hi   there"), "alloy", 1.0)
        p2 = manager._cache_path_for(manager._normalize_tts_text("Hi there"), "alloy", 1.0)

        self.assertEqual(p1.name, p2.name)

    @patch("ai.tts_manager.requests.post")
    def test_synthesize_uses_cache_after_first_generation(self, mock_post: Mock):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.iter_content.return_value = [b"audio-", b"bytes"]

        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=mock_response)
        mock_context.__exit__ = Mock(return_value=None)
        mock_post.return_value = mock_context

        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = TTSManager(api_key="key", model="aura-2-thalia-en", voice="aura-2-thalia-en")
            manager.output_dir = Path(tmp_dir)
            manager.output_dir.mkdir(parents=True, exist_ok=True)

            first = manager.synthesize_to_mp3("hello   world", pace_override=1.0)
            second = manager.synthesize_to_mp3("hello world", pace_override=1.0)

        self.assertTrue(first.endswith(".mp3"))
        self.assertIn("tts_cache_", second)
        self.assertEqual(mock_post.call_count, 1)


if __name__ == "__main__":
    unittest.main()
