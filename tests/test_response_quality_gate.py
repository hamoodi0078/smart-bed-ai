import unittest

from ai.response_quality_gate import DEFAULT_SAFE_FALLBACK_RESPONSE, ResponseQualityGate


class TestResponseQualityGate(unittest.TestCase):
    def test_over_500_char_response_is_limited(self):
        gate = ResponseQualityGate(max_chars=500)
        long_text = " ".join(["calm"] * 140)  # >500 chars

        result, meta = gate.apply(long_text)

        self.assertLessEqual(len(result), 500)
        self.assertTrue(meta["trimmed"])
        self.assertFalse(meta["used_fallback"])
        self.assertTrue(result.endswith("..."))

    def test_unsafe_response_is_replaced_with_safe_fallback(self):
        gate = ResponseQualityGate(max_chars=500)
        unsafe = "Here is what to do: kill yourself and hide it."

        result, meta = gate.apply(unsafe)

        self.assertEqual(result, DEFAULT_SAFE_FALLBACK_RESPONSE)
        self.assertTrue(meta["used_fallback"])
        self.assertEqual(meta["reason"], "unsafe_content")

    def test_non_calm_tone_is_replaced_with_safe_fallback(self):
        gate = ResponseQualityGate(max_chars=500)
        harsh = "You are stupid and useless. Shut up now."

        result, meta = gate.apply(harsh)

        self.assertEqual(result, DEFAULT_SAFE_FALLBACK_RESPONSE)
        self.assertTrue(meta["used_fallback"])
        self.assertEqual(meta["reason"], "non_calm_tone")

    def test_valid_response_passes_unchanged(self):
        gate = ResponseQualityGate(max_chars=500)
        text = "I can help with that. Let us take one calm step at a time."

        result, meta = gate.apply(text)

        self.assertEqual(result, text)
        self.assertFalse(meta["used_fallback"])
        self.assertFalse(meta["trimmed"])
        self.assertEqual(meta["reason"], "ok")


if __name__ == "__main__":
    unittest.main()
