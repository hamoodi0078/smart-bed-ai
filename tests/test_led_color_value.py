import unittest

from led.led_control import LEDController


class TestLedColorValue(unittest.TestCase):
    def test_set_color_value_accepts_natural_phrase_with_punctuation(self):
        led = LEDController()

        led.set_color_value("your favorite color, blue.")

        self.assertEqual(led.user_strip_color, (0, 0, 255))


if __name__ == "__main__":
    unittest.main()
