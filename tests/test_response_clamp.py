import unittest

from main import clamp_non_detail_response


class TestResponseClamp(unittest.TestCase):
    def test_does_not_cut_mid_sentence_when_trimming(self):
        text = (
            "Investing means putting money into assets that can grow over time. "
            "A simple start is broad index funds with regular monthly contributions, low fees, "
            "automatic deposits, risk spread across sectors, and consistent rebalancing discipline over time."
        )

        result = clamp_non_detail_response(text, detailed_mode=False)

        self.assertTrue(result.endswith("."))
        self.assertNotIn("and consistent", result)

    def test_single_long_sentence_uses_ellipsis_not_fake_period(self):
        text = " ".join(["word"] * 45)

        result = clamp_non_detail_response(text, detailed_mode=False)

        self.assertTrue(result.endswith("..."))

    def test_numbered_list_marker_does_not_end_response_early(self):
        text = (
            "There are many black holes in the universe, and they are usually catalog labels. "
            "Here are notable ones: 1. Cygnus X-1 is about 21 solar masses. "
            "2. Sagittarius A* is about 4.3 million solar masses."
        )

        result = clamp_non_detail_response(text, detailed_mode=False, response_style="balanced")

        self.assertIn("Cygnus X-1", result)
        self.assertNotEqual(result.strip(), "Here are notable ones: 1.")


if __name__ == "__main__":
    unittest.main()
