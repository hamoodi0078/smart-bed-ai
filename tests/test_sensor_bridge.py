import unittest
from datetime import datetime

from ai.sensor_bridge import SensorBridge


class TestSensorBridge(unittest.TestCase):
    def test_evening_entry_event_once_per_day(self):
        bridge = SensorBridge()
        now = datetime(2026, 2, 24, 21, 0)

        first = bridge.classify_event(pressure_active=True, motion_active=False, now=now)
        second = bridge.classify_event(pressure_active=True, motion_active=False, now=now)

        self.assertEqual(first, "bed_entered_evening")
        self.assertEqual(second, "")

    def test_morning_wake_event(self):
        bridge = SensorBridge()
        now = datetime(2026, 2, 25, 7, 30)
        event = bridge.classify_event(pressure_active=False, motion_active=True, now=now)

        self.assertEqual(event, "wake_detected_morning")
        line = bridge.proactive_greeting(event, user_name="Dana")
        self.assertIn("good morning", line.lower())


if __name__ == "__main__":
    unittest.main()
