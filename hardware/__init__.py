"""Hardware adapters for optional Raspberry Pi integrations.

Note: MAX30102 wired pulse oximeter has been replaced by the COLMI smart ring
(BLE).  Heart-rate and SpO2 are now provided via ring/ble_client.py.
The pi_heart_rate.py driver is retained as an archive but is no longer wired
into the active system.
"""

from hardware.pi_sensors import (  # noqa: F401
    RaspberryPiSensorMonitor,
    NoopSensorMonitor,
    SensorSnapshot,
    build_sensor_monitor,
)
from hardware.pi_temperature import (  # noqa: F401
    TemperatureSensorMonitor,
    NoopTemperatureMonitor,
    TemperatureReading,
    build_temperature_monitor,
)
