import unittest

from led.led_control import LEDController


class FakeBackend:
    def __init__(self):
        self.frames = []

    def is_available(self) -> bool:
        return True

    def status_line(self) -> str:
        return "fake backend ready"

    def sync(self, frame_state) -> None:
        self.frames.append(frame_state)

    def close(self) -> None:
        return


class TestLedHardwareBackend(unittest.TestCase):
    def test_led_controller_syncs_state_to_backend(self):
        backend = FakeBackend()
        led = LEDController(backend=backend)

        led.set_color_value("blue")
        led.set_user_animation("wave")
        led.set_user_brightness(0.33)
        led.set_state("listening")

        self.assertTrue(backend.frames)
        latest = backend.frames[-1]
        self.assertEqual(latest.user_color, (0, 0, 255))
        self.assertEqual(latest.user_animation, "wave")
        self.assertAlmostEqual(latest.user_brightness, 0.33, places=2)
        self.assertEqual(latest.state_color, (0, 255, 0))
        self.assertTrue(led.hardware_ready())
        self.assertIn("fake backend ready", led.hardware_status())


if __name__ == "__main__":
    unittest.main()
