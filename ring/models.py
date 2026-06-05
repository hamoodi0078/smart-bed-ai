"""Data models for smart ring integration.

All models are frozen dataclasses — immutable, hashable, and safe to pass
across threads.  Every field is typed and has a sensible default so callers
never need to handle missing data explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RingModel(str, Enum):
    """Supported COLMI ring models."""
    R02 = "colmi_r02"
    R06 = "colmi_r06"
    R10 = "colmi_r10"
    UNKNOWN = "unknown"

    @classmethod
    def from_str(cls, value: str) -> "RingModel":
        v = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
        for member in cls:
            if member.value == v or v in member.value:
                return member
        return cls.UNKNOWN


class SleepStage(str, Enum):
    """Sleep stage classification (ring + bed fusion)."""
    DEEP = "deep"
    LIGHT = "light"
    REM = "rem"
    AWAKE = "awake"
    UNKNOWN = "unknown"


class RingConnectionState(str, Enum):
    """BLE connection lifecycle states."""
    DISCONNECTED = "disconnected"
    SCANNING = "scanning"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


# ---------------------------------------------------------------------------
# BLE discovery
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RingDevice:
    """A COLMI ring discovered during BLE scan."""
    address: str = ""        # BLE MAC address (e.g. "AA:BB:CC:DD:EE:FF")
    name: str = ""           # Advertised BLE name (e.g. "R02_XXXX")
    rssi: int = -100         # Signal strength in dBm
    model: RingModel = RingModel.UNKNOWN

    @property
    def signal_quality(self) -> str:
        if self.rssi >= -50:
            return "excellent"
        if self.rssi >= -70:
            return "good"
        if self.rssi >= -85:
            return "fair"
        return "weak"


@dataclass(frozen=True)
class RingDeviceInfo:
    """Detailed info about a connected ring."""
    address: str = ""
    name: str = ""
    model: RingModel = RingModel.UNKNOWN
    firmware_version: str = ""
    battery_pct: int = 0          # 0-100
    last_sync_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "name": self.name,
            "model": self.model.value,
            "firmware_version": self.firmware_version,
            "battery_pct": self.battery_pct,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
        }


# ---------------------------------------------------------------------------
# Real-time readings
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RingHrReading:
    """A single heart-rate reading from the ring."""
    heart_rate_bpm: float = 0.0
    confidence: float = 0.0       # 0.0–1.0
    timestamp: datetime = field(default_factory=_utcnow)
    valid: bool = False

    @property
    def is_resting(self) -> bool:
        """Heuristic: resting HR is typically below 80 bpm in bed."""
        return self.valid and 40 <= self.heart_rate_bpm <= 80


@dataclass(frozen=True)
class RingSpo2Reading:
    """A single SpO₂ reading from the ring."""
    spo2_pct: float = 0.0
    confidence: float = 0.0
    timestamp: datetime = field(default_factory=_utcnow)
    valid: bool = False

    @property
    def is_concerning(self) -> bool:
        """SpO₂ below 90% is a clinical concern."""
        return self.valid and self.spo2_pct < 90.0


@dataclass(frozen=True)
class RingSkinTempReading:
    """Skin temperature reading from the ring."""
    temperature_c: float = 0.0
    timestamp: datetime = field(default_factory=_utcnow)
    valid: bool = False


@dataclass(frozen=True)
class RingAccelReading:
    """Accelerometer movement intensity from the ring (0–100 scale)."""
    intensity: float = 0.0        # 0 = still, 100 = vigorous movement
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    timestamp: datetime = field(default_factory=_utcnow)

    @property
    def is_still(self) -> bool:
        return self.intensity < 5.0


# ---------------------------------------------------------------------------
# Historical data (synced from ring memory)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RingStepRecord:
    """Step count record from ring memory."""
    date: date | None = None
    steps: int = 0
    distance_m: float = 0.0
    calories: float = 0.0


@dataclass(frozen=True)
class RingHrLogEntry:
    """Historical HR data point from ring memory."""
    timestamp: datetime = field(default_factory=_utcnow)
    heart_rate_bpm: float = 0.0
    valid: bool = False


@dataclass(frozen=True)
class RingSleepRecord:
    """One night's ring-recorded sleep data (synced from ring memory).

    This is the ring's own analysis.  The *RingBedFusionEngine* may produce
    a more accurate analysis by combining this with bed sensor data.
    """
    date: date | None = None
    total_minutes: int = 0
    deep_minutes: int = 0
    light_minutes: int = 0
    rem_minutes: int = 0
    awake_minutes: int = 0
    avg_hr_bpm: float = 0.0
    min_hr_bpm: float = 0.0
    max_hr_bpm: float = 0.0
    avg_spo2_pct: float = 0.0
    min_spo2_pct: float = 0.0
    movement_count: int = 0
    skin_temp_avg_c: float | None = None

    @property
    def total_hours(self) -> float:
        return round(self.total_minutes / 60.0, 2)

    @property
    def deep_pct(self) -> float:
        if self.total_minutes <= 0:
            return 0.0
        return round(self.deep_minutes / self.total_minutes * 100.0, 1)

    @property
    def rem_pct(self) -> float:
        if self.total_minutes <= 0:
            return 0.0
        return round(self.rem_minutes / self.total_minutes * 100.0, 1)

    @property
    def light_pct(self) -> float:
        if self.total_minutes <= 0:
            return 0.0
        return round(self.light_minutes / self.total_minutes * 100.0, 1)

    @property
    def sleep_efficiency(self) -> float:
        """Ratio of actual sleep to total time in bed (%)."""
        total = self.total_minutes
        if total <= 0:
            return 0.0
        sleep = total - self.awake_minutes
        return round(max(0.0, sleep / total * 100.0), 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date.isoformat() if self.date else None,
            "total_minutes": self.total_minutes,
            "total_hours": self.total_hours,
            "deep_minutes": self.deep_minutes,
            "deep_pct": self.deep_pct,
            "light_minutes": self.light_minutes,
            "light_pct": self.light_pct,
            "rem_minutes": self.rem_minutes,
            "rem_pct": self.rem_pct,
            "awake_minutes": self.awake_minutes,
            "sleep_efficiency": self.sleep_efficiency,
            "avg_hr_bpm": self.avg_hr_bpm,
            "min_hr_bpm": self.min_hr_bpm,
            "max_hr_bpm": self.max_hr_bpm,
            "avg_spo2_pct": self.avg_spo2_pct,
            "min_spo2_pct": self.min_spo2_pct,
            "movement_count": self.movement_count,
            "skin_temp_avg_c": self.skin_temp_avg_c,
        }


# ---------------------------------------------------------------------------
# Unified biometrics (ring + bed fused)
# ---------------------------------------------------------------------------

@dataclass
class UnifiedBiometrics:
    """Combined snapshot from ring and bed sensors.

    Every field is optional — the fusion engine fills what it can.
    """
    # Ring biometrics
    ring_connected: bool = False
    ring_battery_pct: int = 0
    heart_rate_bpm: float | None = None
    heart_rate_source: str = ""          # "ring", "bed_max30102", "none"
    spo2_pct: float | None = None
    spo2_source: str = ""
    skin_temp_c: float | None = None
    ring_movement_intensity: float | None = None

    # Bed sensors
    bed_pressure_active: bool = False
    bed_motion_active: bool = False
    room_temp_c: float | None = None
    room_humidity_pct: float | None = None

    # Fused intelligence
    current_sleep_stage: SleepStage = SleepStage.UNKNOWN
    stress_indicator: float | None = None      # 0–100
    recovery_readiness: float | None = None    # 0–100
    is_asleep: bool = False
    is_in_bed: bool = False
    asleep_since: datetime | None = None

    timestamp: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ring_connected": self.ring_connected,
            "ring_battery_pct": self.ring_battery_pct,
            "heart_rate_bpm": self.heart_rate_bpm,
            "heart_rate_source": self.heart_rate_source,
            "spo2_pct": self.spo2_pct,
            "spo2_source": self.spo2_source,
            "skin_temp_c": self.skin_temp_c,
            "ring_movement_intensity": self.ring_movement_intensity,
            "bed_pressure_active": self.bed_pressure_active,
            "bed_motion_active": self.bed_motion_active,
            "room_temp_c": self.room_temp_c,
            "room_humidity_pct": self.room_humidity_pct,
            "current_sleep_stage": self.current_sleep_stage.value,
            "stress_indicator": self.stress_indicator,
            "recovery_readiness": self.recovery_readiness,
            "is_asleep": self.is_asleep,
            "is_in_bed": self.is_in_bed,
            "asleep_since": self.asleep_since.isoformat() if self.asleep_since else None,
            "timestamp": self.timestamp.isoformat(),
        }
