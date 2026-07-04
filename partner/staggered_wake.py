"""Staggered wake routine manager for Smart Bed AI partner mode.

Handles different wake times for two partners sharing the bed,
using side-specific LED control, vibration-only alarms, and
minimal-disturbance wake sequences.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("partner.staggered_wake")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_hhmm(text: str) -> tuple[int, int] | None:
    text = str(text or "").strip()
    if ":" not in text:
        return None
    try:
        parts = text.split(":")
        return max(0, min(23, int(parts[0]))), max(0, min(59, int(parts[1])))
    except Exception:
        return None


class StaggeredWake:
    """Manages staggered wake routines for dual-partner bed occupancy."""

    def __init__(
        self,
        *,
        min_stagger_minutes: int = 15,
        silent_wake_brightness: float = 0.03,
        silent_wake_duration_minutes: int = 10,
    ):
        self._min_stagger = max(5, int(min_stagger_minutes))
        self._silent_brightness = max(0.01, min(0.10, float(silent_wake_brightness)))
        self._silent_duration = max(5, int(silent_wake_duration_minutes))
        self._first_wake_triggered = False
        self._second_wake_triggered = False

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("partner_mode", {})
        pm = profile["partner_mode"]
        pm.setdefault("partner1", {}).setdefault("wake_time", "07:00")
        pm.setdefault("partner2", {}).setdefault("wake_time", "07:00")
        pm.setdefault(
            "staggered_wake",
            {
                "enabled": True,
                "snooze_escalation": True,
                "vibration_enabled": True,
            },
        )

    # ------------------------------------------------------------------
    # Wake schedule computation
    # ------------------------------------------------------------------

    def compute_wake_schedule(self, profile: dict) -> dict[str, Any]:
        """Compute the staggered wake schedule for both partners."""
        self.ensure_shape(profile)
        pm = profile.get("partner_mode", {})

        p1_time = _parse_hhmm(pm.get("partner1", {}).get("wake_time", "07:00"))
        p2_time = _parse_hhmm(pm.get("partner2", {}).get("wake_time", "07:00"))

        if not p1_time or not p2_time:
            return {"available": False, "reason": "Invalid wake times."}

        p1_minutes = p1_time[0] * 60 + p1_time[1]
        p2_minutes = p2_time[0] * 60 + p2_time[1]

        diff = abs(p1_minutes - p2_minutes)
        staggered = diff >= self._min_stagger

        if p1_minutes <= p2_minutes:
            first = "partner1"
            second = "partner2"
            first_time = f"{p1_time[0]:02d}:{p1_time[1]:02d}"
            second_time = f"{p2_time[0]:02d}:{p2_time[1]:02d}"
            first_side = str(pm.get("partner1", {}).get("side", "left"))
            second_side = str(pm.get("partner2", {}).get("side", "right"))
        else:
            first = "partner2"
            second = "partner1"
            first_time = f"{p2_time[0]:02d}:{p2_time[1]:02d}"
            second_time = f"{p1_time[0]:02d}:{p1_time[1]:02d}"
            first_side = str(pm.get("partner2", {}).get("side", "right"))
            second_side = str(pm.get("partner1", {}).get("side", "left"))

        return {
            "available": True,
            "staggered": staggered,
            "difference_minutes": diff,
            "first_waker": {
                "partner": first,
                "name": pm.get(first, {}).get("name", first),
                "wake_time": first_time,
                "side": first_side,
                "wake_type": "silent" if staggered else "normal",
            },
            "second_waker": {
                "partner": second,
                "name": pm.get(second, {}).get("name", second),
                "wake_time": second_time,
                "side": second_side,
                "wake_type": "normal",
            },
        }

    # ------------------------------------------------------------------
    # Wake sequence generation
    # ------------------------------------------------------------------

    def get_first_wake_sequence(self, profile: dict) -> list[dict[str, Any]]:
        """Generate minimal-disturbance wake sequence for the first waker."""
        schedule = self.compute_wake_schedule(profile)
        if not schedule.get("staggered", False):
            return self._normal_wake_sequence(schedule.get("first_waker", {}))

        first = schedule.get("first_waker", {})
        side = first.get("side", "left")
        other_side = "right" if side == "left" else "left"

        return [
            {
                "phase": "silent_approach",
                "offset_minutes": -self._silent_duration,
                "actions": [
                    {
                        "type": "zoned_led",
                        "zone": side,
                        "brightness": self._silent_brightness * 0.5,
                        "color": "#FFB347",
                        "animation": "very_slow_fade_in",
                    },
                    {
                        "type": "zoned_led",
                        "zone": other_side,
                        "brightness": 0.0,
                        "color": "#000000",
                        "animation": "off",
                    },
                ],
            },
            {
                "phase": "silent_ramp",
                "offset_minutes": -5,
                "actions": [
                    {
                        "type": "zoned_led",
                        "zone": side,
                        "brightness": self._silent_brightness,
                        "color": "#FFDAB9",
                        "animation": "slow_fade_in",
                    }
                ],
            },
            {
                "phase": "vibration_wake",
                "offset_minutes": 0,
                "actions": [
                    {
                        "type": "vibration",
                        "zone": side,
                        "pattern": "gentle_pulse",
                        "intensity": 0.3,
                        "duration_seconds": 10,
                    },
                    {
                        "type": "zoned_led",
                        "zone": side,
                        "brightness": self._silent_brightness * 2,
                        "color": "#FFF8DC",
                        "animation": "solid",
                    },
                ],
            },
            {
                "phase": "post_wake",
                "offset_minutes": 2,
                "actions": [
                    {
                        "type": "voice",
                        "message": f"Good morning, {first.get('name', '')}.",
                        "volume": 0.15,
                        "zone": side,
                    }
                ],
                "condition": "first_partner_exited_bed",
            },
        ]

    def get_second_wake_sequence(self, profile: dict) -> list[dict[str, Any]]:
        """Generate normal wake sequence for the second waker (partner already up)."""
        schedule = self.compute_wake_schedule(profile)
        second = schedule.get("second_waker", {})
        return self._normal_wake_sequence(second)

    def on_first_partner_exit(self, profile: dict) -> dict[str, Any]:
        """Called when first partner exits bed after their alarm."""
        self._first_wake_triggered = True
        schedule = self.compute_wake_schedule(profile)
        second = schedule.get("second_waker", {})

        return {
            "first_exited": True,
            "actions": [
                {
                    "type": "led_scene",
                    "action": "restore_sleep_mode",
                    "brightness": 0.0,
                    "animation": "fade_to_black",
                    "duration_seconds": 30,
                },
                {
                    "type": "system",
                    "message": f"Sleep mode restored for {second.get('name', 'partner')}.",
                },
            ],
            "second_alarm_at": second.get("wake_time", ""),
        }

    # ------------------------------------------------------------------
    # Snooze handling
    # ------------------------------------------------------------------

    def handle_snooze(self, profile: dict, partner: str, snooze_minutes: int = 5) -> dict[str, Any]:
        """Handle snooze for a partner with escalation awareness."""
        self.ensure_shape(profile)
        sw = profile["partner_mode"].get("staggered_wake", {})
        schedule = self.compute_wake_schedule(profile)

        is_first = partner == schedule.get("first_waker", {}).get("partner", "")
        other_partner = (
            schedule.get("second_waker", {}) if is_first else schedule.get("first_waker", {})
        )

        snooze_min = max(3, min(15, int(snooze_minutes)))

        actions: list[dict[str, Any]] = [
            {"type": "led_scene", "action": "fade_out", "brightness": 0.0, "duration_seconds": 10},
        ]

        if is_first and sw.get("snooze_escalation", True):
            actions.append(
                {
                    "type": "notification",
                    "message": f"Snooze for {snooze_min} min. Using vibration-only to not disturb {other_partner.get('name', 'partner')}.",
                    "priority": "low",
                }
            )

        return {
            "snoozed": True,
            "partner": partner,
            "snooze_minutes": snooze_min,
            "next_alarm_type": "vibration_only" if is_first else "normal",
            "actions": actions,
        }

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self, profile: dict) -> dict[str, Any]:
        self.ensure_shape(profile)
        schedule = self.compute_wake_schedule(profile)
        return {
            "enabled": profile.get("partner_mode", {})
            .get("staggered_wake", {})
            .get("enabled", True),
            "schedule": schedule,
            "first_wake_triggered": self._first_wake_triggered,
            "second_wake_triggered": self._second_wake_triggered,
        }

    def reset(self) -> None:
        """Reset wake state for new night."""
        self._first_wake_triggered = False
        self._second_wake_triggered = False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normal_wake_sequence(partner_info: dict) -> list[dict[str, Any]]:
        name = partner_info.get("name", "")
        return [
            {
                "phase": "gentle_approach",
                "offset_minutes": -15,
                "actions": [
                    {
                        "type": "led_scene",
                        "brightness": 0.05,
                        "color": "#FFB347",
                        "animation": "slow_fade_in",
                    },
                    {"type": "audio", "sound": "nature_ambient", "volume": 0.1},
                ],
            },
            {
                "phase": "sunrise",
                "offset_minutes": -10,
                "actions": [
                    {
                        "type": "led_scene",
                        "brightness": 0.15,
                        "color": "#FFDAB9",
                        "animation": "sunrise",
                    },
                    {"type": "audio", "sound": "birds_chirping", "volume": 0.3},
                ],
            },
            {
                "phase": "morning_light",
                "offset_minutes": -5,
                "actions": [
                    {
                        "type": "led_scene",
                        "brightness": 0.35,
                        "color": "#FFF8DC",
                        "animation": "solid",
                    },
                    {"type": "audio", "sound": "gentle_stream", "volume": 0.5},
                ],
            },
            {
                "phase": "full_wake",
                "offset_minutes": 0,
                "actions": [
                    {
                        "type": "led_scene",
                        "brightness": 0.70,
                        "color": "#F5F5F5",
                        "animation": "solid",
                    },
                    {"type": "audio", "sound": "morning_energy", "volume": 0.7},
                    {
                        "type": "voice",
                        "message": f"Bismillah. Good morning{', ' + name if name else ''}! Time to rise.",
                        "volume": 0.6,
                    },
                ],
            },
        ]
