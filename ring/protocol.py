"""COLMI R02/R06 BLE packet protocol — encode commands and decode responses.

Based on the reverse-engineered protocol documented at:
  https://github.com/tahnok/colmi_r02_client

All COLMI rings communicate via a Nordic UART Service (NUS) with 16-byte
packets.  This module handles the low-level byte encoding/decoding so the
BLE client can work with typed Python objects.

Packet structure:
  Byte 0:     Tag (command identifier)
  Bytes 1-14: Payload (command-specific)
  Byte 15:    Checksum (XOR of bytes 0-14)
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import struct
from datetime import datetime, timezone
from typing import Any

from ring.models import (
    RingHrLogEntry,
    RingHrReading,
    RingSleepRecord,
    RingSpo2Reading,
    RingStepRecord,
)


# ---------------------------------------------------------------------------
# Constants — COLMI R02 GATT Service/Characteristic UUIDs
# ---------------------------------------------------------------------------

COLMI_SERVICE_UUID = "6e40fff0-b5a3-f393-e0a9-e50e24dcca9e"
COLMI_TX_CHAR_UUID = "6e40fff1-b5a3-f393-e0a9-e50e24dcca9e"   # Write to ring
COLMI_RX_CHAR_UUID = "6e40fff2-b5a3-f393-e0a9-e50e24dcca9e"   # Receive from ring

# BLE device name prefixes for COLMI rings
COLMI_NAME_PREFIXES = ("R02", "R06", "R10", "COLMI", "QRing")

# Packet tags (command IDs)
TAG_SET_TIME = 0x01
TAG_BATTERY = 0x03
TAG_DEVICE_INFO = 0x04
TAG_HEART_RATE_LOG = 0x15
TAG_SPO2_LOG = 0x16
TAG_STEP_LOG = 0x0D
TAG_SLEEP_LOG = 0x17
TAG_REALTIME_HR_START = 0x69
TAG_REALTIME_HR_STOP = 0x6A
TAG_REALTIME_HR_DATA = 0x6B
TAG_REALTIME_SPO2_START = 0x70
TAG_REALTIME_SPO2_STOP = 0x71
TAG_REALTIME_SPO2_DATA = 0x72
TAG_TEMPERATURE = 0x24
TAG_SPORT_DETAIL = 0x42

PACKET_SIZE = 16


# ---------------------------------------------------------------------------
# Checksum
# ---------------------------------------------------------------------------

def _checksum(data: bytes) -> int:
    """XOR checksum of all bytes (COLMI protocol)."""
    result = 0
    for b in data:
        result ^= b
    return result & 0xFF


def _build_packet(tag: int, payload: bytes = b"") -> bytes:
    """Build a 16-byte COLMI command packet.

    Pads payload with zeros if shorter than 14 bytes, adds XOR checksum.
    """
    if len(payload) > 14:
        payload = payload[:14]
    raw = bytes([tag]) + payload.ljust(14, b"\x00")
    return raw + bytes([_checksum(raw)])


def _validate_packet(data: bytes) -> bool:
    """Validate a received 16-byte packet checksum."""
    if len(data) != PACKET_SIZE:
        return False
    expected = _checksum(data[:15])
    return data[15] == expected


# ---------------------------------------------------------------------------
# Command builders — send TO ring
# ---------------------------------------------------------------------------

def cmd_set_time(dt: datetime | None = None) -> bytes:
    """Build a SET_TIME command to sync the ring's clock."""
    dt = dt or datetime.now(timezone.utc)
    payload = struct.pack(
        "<BBBBBB",
        dt.year - 2000,
        dt.month,
        dt.day,
        dt.hour,
        dt.minute,
        dt.second,
    )
    return _build_packet(TAG_SET_TIME, payload)


def cmd_battery() -> bytes:
    """Request battery level."""
    return _build_packet(TAG_BATTERY)


def cmd_device_info() -> bytes:
    """Request device info (firmware version, model)."""
    return _build_packet(TAG_DEVICE_INFO)


def cmd_start_realtime_hr() -> bytes:
    """Start continuous heart-rate streaming."""
    return _build_packet(TAG_REALTIME_HR_START)


def cmd_stop_realtime_hr() -> bytes:
    """Stop continuous heart-rate streaming."""
    return _build_packet(TAG_REALTIME_HR_STOP)


def cmd_start_realtime_spo2() -> bytes:
    """Start continuous SpO₂ streaming."""
    return _build_packet(TAG_REALTIME_SPO2_START)


def cmd_stop_realtime_spo2() -> bytes:
    """Stop continuous SpO₂ streaming."""
    return _build_packet(TAG_REALTIME_SPO2_STOP)


def cmd_read_hr_log(day_offset: int = 0) -> bytes:
    """Request HR log for a specific day (0 = today, 1 = yesterday, ...)."""
    payload = struct.pack("<B", min(255, max(0, int(day_offset))))
    return _build_packet(TAG_HEART_RATE_LOG, payload)


def cmd_read_spo2_log(day_offset: int = 0) -> bytes:
    """Request SpO₂ log for a specific day."""
    payload = struct.pack("<B", min(255, max(0, int(day_offset))))
    return _build_packet(TAG_SPO2_LOG, payload)


def cmd_read_step_log(day_offset: int = 0) -> bytes:
    """Request step count log for a specific day."""
    payload = struct.pack("<B", min(255, max(0, int(day_offset))))
    return _build_packet(TAG_STEP_LOG, payload)


def cmd_read_sleep_log(day_offset: int = 0) -> bytes:
    """Request sleep data for a specific day."""
    payload = struct.pack("<B", min(255, max(0, int(day_offset))))
    return _build_packet(TAG_SLEEP_LOG, payload)


def cmd_read_temperature() -> bytes:
    """Request skin temperature reading."""
    return _build_packet(TAG_TEMPERATURE)


# ---------------------------------------------------------------------------
# Response parsers — received FROM ring
# ---------------------------------------------------------------------------

def parse_tag(data: bytes) -> int:
    """Extract the command tag from a 16-byte packet."""
    if len(data) < 1:
        return 0
    return data[0]


def parse_battery(data: bytes) -> int:
    """Parse battery response → battery percent (0–100)."""
    if len(data) < 3:
        return 0
    # Byte 1: charging flag, Byte 2: battery percent
    return max(0, min(100, data[2]))


def parse_device_info(data: bytes) -> dict[str, str]:
    """Parse device info → firmware version, model string."""
    if len(data) < 8:
        return {"firmware_version": "unknown", "model": "unknown"}
    # Typical: bytes 1-4 are version digits
    major = data[1]
    minor = data[2]
    patch = data[3]
    return {
        "firmware_version": f"{major}.{minor:02d}.{patch:02d}",
        "model": "colmi_r02",  # Refine from BLE name at connection time
    }


def parse_realtime_hr(data: bytes) -> RingHrReading:
    """Parse a realtime HR notification → RingHrReading."""
    if len(data) < 4:
        return RingHrReading()
    hr_value = data[1]
    confidence_raw = data[2]  # 0–255 mapped to 0–1
    if hr_value == 0 or hr_value == 255:
        return RingHrReading(heart_rate_bpm=0.0, confidence=0.0, valid=False)
    return RingHrReading(
        heart_rate_bpm=float(hr_value),
        confidence=round(confidence_raw / 255.0, 2),
        valid=True,
    )


def parse_realtime_spo2(data: bytes) -> RingSpo2Reading:
    """Parse a realtime SpO₂ notification → RingSpo2Reading."""
    if len(data) < 4:
        return RingSpo2Reading()
    spo2_value = data[1]
    confidence_raw = data[2]
    if spo2_value == 0 or spo2_value == 255:
        return RingSpo2Reading(spo2_pct=0.0, confidence=0.0, valid=False)
    return RingSpo2Reading(
        spo2_pct=float(spo2_value),
        confidence=round(confidence_raw / 255.0, 2),
        valid=True,
    )


def parse_temperature(data: bytes) -> float | None:
    """Parse skin temperature → Celsius or None."""
    if len(data) < 4:
        return None
    # Temperature stored as integer * 10 (e.g., 362 = 36.2°C)
    temp_raw = struct.unpack_from("<H", data, 1)[0]
    if temp_raw == 0 or temp_raw > 450:  # sanity: 0–45°C
        return None
    return round(temp_raw / 10.0, 1)


def parse_hr_log(data: bytes, base_date: datetime | None = None) -> list[RingHrLogEntry]:
    """Parse HR log response into a list of timestamped readings.

    The ring stores HR readings at ~5-minute intervals.  Each log packet
    contains up to 14 readings (one per payload byte after the tag).
    """
    if len(data) < 2:
        return []
    base = base_date or datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
    entries: list[RingHrLogEntry] = []
    for i in range(1, min(15, len(data))):
        hr = data[i]
        if hr == 0 or hr == 255:
            continue
        ts = base.replace(minute=0) + __import__("datetime").timedelta(minutes=(i - 1) * 5)
        entries.append(RingHrLogEntry(
            timestamp=ts,
            heart_rate_bpm=float(hr),
            valid=True,
        ))
    return entries


def parse_sleep_log(data: bytes, sleep_date: Any = None) -> RingSleepRecord | None:
    """Parse a sleep log packet.

    The COLMI sleep log encodes total, deep, light, REM, and awake minutes,
    plus aggregate HR and SpO₂ stats.  Format varies slightly by firmware.
    """
    if len(data) < 12:
        return None
    try:
        total_min = struct.unpack_from("<H", data, 1)[0]
        deep_min = data[3]
        light_min = data[4]
        rem_min = data[5]
        awake_min = data[6]
        avg_hr = data[7]
        min_hr = data[8]
        avg_spo2 = data[9]
        min_spo2 = data[10]
        movement = data[11]

        if total_min == 0:
            return None

        from datetime import date as date_type
        d = sleep_date if isinstance(sleep_date, date_type) else None

        return RingSleepRecord(
            date=d,
            total_minutes=int(total_min),
            deep_minutes=int(deep_min),
            light_minutes=int(light_min),
            rem_minutes=int(rem_min),
            awake_minutes=int(awake_min),
            avg_hr_bpm=float(avg_hr),
            min_hr_bpm=float(min_hr),
            max_hr_bpm=0.0,
            avg_spo2_pct=float(avg_spo2),
            min_spo2_pct=float(min_spo2),
            movement_count=int(movement),
        )
    except Exception:
        return None


def parse_step_log(data: bytes, step_date: Any = None) -> RingStepRecord | None:
    """Parse a step log packet."""
    if len(data) < 8:
        return None
    try:
        steps = struct.unpack_from("<H", data, 1)[0]
        distance = struct.unpack_from("<H", data, 3)[0]  # meters
        calories = struct.unpack_from("<H", data, 5)[0]

        from datetime import date as date_type
        d = step_date if isinstance(step_date, date_type) else None

        return RingStepRecord(
            date=d,
            steps=int(steps),
            distance_m=float(distance),
            calories=float(calories),
        )
    except Exception:
        return None
