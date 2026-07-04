import time
import unittest
from unittest.mock import patch

from hardware.pi_sensors import RaspberryPiSensorMonitor, SensorSnapshot


class FakeInputDevice:
    def __init__(self, pin: int, pull_up: bool = False):
        self.pin = pin
        self.pull_up = pull_up
        self.value = 1 if pull_up else 0

    def close(self):
        return


class TestPiSensors(unittest.TestCase):
    def test_snapshot_respects_active_low_and_active_high_inputs(self):
        devices = {}

        def factory(pin: int, pull_up: bool = False):
            device = FakeInputDevice(pin=pin, pull_up=pull_up)
            devices[pin] = device
            return device

        with patch("hardware.pi_sensors.sys.platform", "linux"):
            monitor = RaspberryPiSensorMonitor(
                pressure_enabled=True,
                pressure_pin=23,
                pressure_pull_up=True,
                pressure_active_low=True,
                motion_enabled=True,
                motion_pin=24,
                motion_pull_up=False,
                motion_active_low=False,
                poll_interval_seconds=0.05,
                input_factory=factory,
            )

        self.assertTrue(monitor.is_available())
        self.assertEqual(
            monitor.snapshot(), SensorSnapshot(pressure_active=False, motion_active=False)
        )

        devices[23].value = 0
        devices[24].value = 1
        self.assertEqual(
            monitor.snapshot(), SensorSnapshot(pressure_active=True, motion_active=True)
        )
        monitor.close()

    def test_monitor_emits_callback_when_input_changes(self):
        devices = {}

        def factory(pin: int, pull_up: bool = False):
            device = FakeInputDevice(pin=pin, pull_up=pull_up)
            devices[pin] = device
            return device

        seen = []

        with patch("hardware.pi_sensors.sys.platform", "linux"):
            monitor = RaspberryPiSensorMonitor(
                pressure_enabled=True,
                pressure_pin=23,
                pressure_pull_up=True,
                pressure_active_low=True,
                motion_enabled=False,
                motion_pin=-1,
                motion_pull_up=False,
                motion_active_low=False,
                poll_interval_seconds=0.02,
                input_factory=factory,
            )

        monitor.start(seen.append)
        devices[23].value = 0
        time.sleep(0.08)
        monitor.close()

        self.assertTrue(seen)
        self.assertIn(SensorSnapshot(pressure_active=True, motion_active=False), seen)


if __name__ == "__main__":
    unittest.main()
