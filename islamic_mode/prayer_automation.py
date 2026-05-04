"""Intelligent prayer time automation for Smart Bed AI.

Automates pre-prayer preparation (dim lights, pause music), prayer-time LED colors,
Qibla direction indicators, and post-prayer restoration. Integrates with the
existing PrayerTimesService.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any

from islamic_mode.prayer_times import PrayerTimesService

logger = logging.getLogger("islamic_mode.prayer_automation")

PRAYER_LED_COLORS = {
    "Fajr": {"hex": "#FFF5E0", "name": "soft_golden", "brightness": 0.15},
    "Dhuhr": {"hex": "#FFFFFF", "name": "bright_white", "brightness": 0.40},
    "Asr": {"hex": "#FFD700", "name": "warm_gold", "brightness": 0.35},
    "Maghrib": {"hex": "#FF6B35", "name": "orange_red", "brightness": 0.30},
    "Isha": {"hex": "#7B68EE", "name": "deep_purple", "brightness": 0.20},
}

PRAYER_ORDER = ("Fajr", "Dhuhr", "Asr", "Maghrib", "Isha")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_hhmm(text: str) -> tuple[int, int] | None:
    text = str(text or "").strip()
    if ":" not in text:
        return None
    try:
        parts = text.split(":")
        return int(parts[0]), int(parts[1])
    except Exception:
        return None


def _minutes_until(target_hhmm: str, now: datetime) -> int | None:
    parsed = _parse_hhmm(target_hhmm)
    if parsed is None:
        return None
    h, m = parsed
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    delta = int((target - now).total_seconds() // 60)
    return delta


def calculate_qibla_bearing(latitude: float, longitude: float) -> float:
    """Calculate Qibla direction (bearing to Mecca) from given coordinates."""
    kaaba_lat = math.radians(21.4225)
    kaaba_lon = math.radians(39.8262)
    lat = math.radians(latitude)
    lon = math.radians(longitude)
    d_lon = kaaba_lon - lon
    x = math.sin(d_lon) * math.cos(kaaba_lat)
    y = math.cos(lat) * math.sin(kaaba_lat) - math.sin(lat) * math.cos(kaaba_lat) * math.cos(d_lon)
    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360


class PrayerAutomation:
    """Manages automated prayer-time actions: LED, notifications, music pause, Qibla."""

    def __init__(
        self,
        prayer_service: PrayerTimesService | None = None,
        *,
        pre_prayer_minutes: int = 10,
        prayer_mat_duration_minutes: int = 30,
    ):
        self._prayer_service = prayer_service or PrayerTimesService()
        self._pre_prayer_minutes = max(3, int(pre_prayer_minutes))
        self._prayer_mat_duration = max(10, int(prayer_mat_duration_minutes))
        self._last_actions: dict[str, str] = {}
        self._prayer_mat_active = False
        self._prayer_mat_started_at: datetime | None = None

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("islamic", {})
        islamic = profile["islamic"]
        islamic.setdefault("prayer_automation_enabled", True)
        islamic.setdefault("pre_prayer_notification_enabled", True)
        islamic.setdefault("auto_pause_music", True)
        islamic.setdefault("prayer_led_enabled", True)
        islamic.setdefault("qibla_indicator_enabled", True)
        islamic.setdefault("adhan_playback_enabled", False)
        islamic.setdefault("prayer_mat_mode_enabled", True)
        islamic.setdefault("last_prayer_actions", {})
        islamic.setdefault("prayer_stats", {
            "total_reminders_sent": 0,
            "acknowledged_count": 0,
        })

    # ------------------------------------------------------------------
    # Core evaluation (called periodically by automation loop)
    # ------------------------------------------------------------------

    def evaluate(self, profile: dict, now: datetime | None = None) -> list[dict[str, Any]]:
        """Evaluate all prayer automations and return actions to execute."""
        now = now or datetime.now()
        self.ensure_shape(profile)
        islamic = profile.get("islamic", {})
        if not islamic.get("prayer_automation_enabled", True):
            return []

        actions: list[dict[str, Any]] = []

        try:
            prayers = self._prayer_service.get_today_prayers()
        except Exception as exc:
            logger.error("Failed to fetch prayer times: %s", exc)
            return []

        for prayer_name in PRAYER_ORDER:
            prayer_time = prayers.get(prayer_name, "")
            if not prayer_time:
                continue

            minutes = _minutes_until(prayer_time, now)
            if minutes is None:
                continue

            today_key = f"{now.date().isoformat()}:{prayer_name}"

            # Pre-prayer preparation
            if 0 < minutes <= self._pre_prayer_minutes:
                action_key = f"{today_key}:pre"
                if action_key not in self._last_actions:
                    pre_actions = self._build_pre_prayer_actions(profile, prayer_name, minutes)
                    actions.extend(pre_actions)
                    self._last_actions[action_key] = now.isoformat()

            # At prayer time
            if -2 <= minutes <= 0:
                action_key = f"{today_key}:at"
                if action_key not in self._last_actions:
                    at_actions = self._build_prayer_time_actions(profile, prayer_name)
                    actions.extend(at_actions)
                    self._last_actions[action_key] = now.isoformat()
                    islamic["prayer_stats"]["total_reminders_sent"] = (
                        int(islamic["prayer_stats"].get("total_reminders_sent", 0)) + 1
                    )

        self._cleanup_old_actions(now)
        self._check_prayer_mat_timeout(now)

        return actions

    # ------------------------------------------------------------------
    # Action builders
    # ------------------------------------------------------------------

    def _build_pre_prayer_actions(
        self, profile: dict, prayer_name: str, minutes_until: int
    ) -> list[dict[str, Any]]:
        islamic = profile.get("islamic", {})
        actions: list[dict[str, Any]] = []

        if islamic.get("pre_prayer_notification_enabled", True):
            actions.append({
                "type": "notification",
                "category": "prayer_reminder",
                "prayer": prayer_name,
                "message": f"{prayer_name} prayer in {minutes_until} minutes.",
                "priority": "high",
            })

        if islamic.get("auto_pause_music", True):
            actions.append({
                "type": "music_control",
                "action": "pause",
                "reason": f"Pre-{prayer_name} preparation",
            })

        actions.append({
            "type": "led_scene",
            "action": "dim_for_prayer",
            "brightness": 0.20,
            "color": "#FFF8DC",
            "animation": "breathing",
            "reason": f"Preparing for {prayer_name}",
        })

        if islamic.get("qibla_indicator_enabled", True):
            lat = float(profile.get("preferences", {}).get("latitude", 0) or 0)
            lon = float(profile.get("preferences", {}).get("longitude", 0) or 0)
            if lat != 0 or lon != 0:
                bearing = calculate_qibla_bearing(lat, lon)
                actions.append({
                    "type": "qibla_indicator",
                    "bearing_degrees": round(bearing, 1),
                    "prayer": prayer_name,
                })

        return actions

    def _build_prayer_time_actions(self, profile: dict, prayer_name: str) -> list[dict[str, Any]]:
        islamic = profile.get("islamic", {})
        actions: list[dict[str, Any]] = []
        color_info = PRAYER_LED_COLORS.get(prayer_name, PRAYER_LED_COLORS["Dhuhr"])

        if islamic.get("prayer_led_enabled", True):
            actions.append({
                "type": "led_scene",
                "action": "prayer_color",
                "color": color_info["hex"],
                "brightness": color_info["brightness"],
                "animation": "gentle_pulse",
                "prayer": prayer_name,
            })

        if islamic.get("adhan_playback_enabled", False):
            actions.append({
                "type": "audio",
                "action": "play_adhan",
                "prayer": prayer_name,
                "volume": 0.5,
            })

        actions.append({
            "type": "voice",
            "message": self._prayer_voice_message(prayer_name),
            "prayer": prayer_name,
        })

        return actions

    @staticmethod
    def _prayer_voice_message(prayer_name: str) -> str:
        messages = {
            "Fajr": "Fajr time. Rise gently, make wudu, and begin your day with prayer.",
            "Dhuhr": "Dhuhr prayer time. Take a moment to pray and refresh.",
            "Asr": "Asr prayer time. Pause your afternoon and connect with Allah.",
            "Maghrib": "Maghrib prayer time. The sun has set. Time to pray.",
            "Isha": "Isha prayer time. Complete your daily prayers before rest.",
        }
        return messages.get(prayer_name, f"{prayer_name} prayer time.")

    # ------------------------------------------------------------------
    # Prayer mat mode
    # ------------------------------------------------------------------

    def activate_prayer_mat_mode(self, profile: dict) -> dict[str, Any]:
        """Activate ultra-quiet prayer mode: dim lights, silence, timer."""
        self.ensure_shape(profile)
        self._prayer_mat_active = True
        self._prayer_mat_started_at = _utcnow()

        return {
            "active": True,
            "brightness": 0.05,
            "silent_mode": True,
            "duration_minutes": self._prayer_mat_duration,
            "auto_deactivate_at": (
                self._prayer_mat_started_at + timedelta(minutes=self._prayer_mat_duration)
            ).isoformat(),
            "actions": [
                {"type": "led_scene", "brightness": 0.05, "color": "#FFF8DC", "animation": "solid"},
                {"type": "quiet_mode", "enabled": True},
                {"type": "notifications", "suppress": True},
            ],
        }

    def deactivate_prayer_mat_mode(self) -> dict[str, Any]:
        self._prayer_mat_active = False
        self._prayer_mat_started_at = None
        return {
            "active": False,
            "actions": [
                {"type": "quiet_mode", "enabled": False},
                {"type": "notifications", "suppress": False},
                {"type": "led_scene", "action": "restore_previous"},
            ],
        }

    def is_prayer_mat_active(self) -> bool:
        return self._prayer_mat_active

    def _check_prayer_mat_timeout(self, now: datetime) -> None:
        if not self._prayer_mat_active or self._prayer_mat_started_at is None:
            return
        elapsed = (now - self._prayer_mat_started_at).total_seconds() / 60.0
        if elapsed >= self._prayer_mat_duration:
            self.deactivate_prayer_mat_mode()
            logger.info("Prayer mat mode auto-deactivated after %d minutes", self._prayer_mat_duration)

    # ------------------------------------------------------------------
    # Prayer acknowledgment
    # ------------------------------------------------------------------

    def acknowledge_prayer(self, profile: dict, prayer_name: str) -> dict[str, Any]:
        """Record that user acknowledged a prayer reminder."""
        self.ensure_shape(profile)
        islamic = profile["islamic"]
        islamic["prayer_stats"]["acknowledged_count"] = (
            int(islamic["prayer_stats"].get("acknowledged_count", 0)) + 1
        )
        total = int(islamic["prayer_stats"].get("total_reminders_sent", 0))
        ack = int(islamic["prayer_stats"].get("acknowledged_count", 0))
        rate = round(ack / total * 100, 1) if total > 0 else 0

        return {
            "acknowledged": True,
            "prayer": prayer_name,
            "total_acknowledged": ack,
            "acknowledgment_rate": rate,
        }

    # ------------------------------------------------------------------
    # Friday special
    # ------------------------------------------------------------------

    def get_friday_actions(self, profile: dict, now: datetime | None = None) -> list[dict[str, Any]]:
        """Return special Friday (Jummah) automation actions."""
        now = now or datetime.now()
        if now.weekday() != 4:  # 4 = Friday
            return []

        self.ensure_shape(profile)
        today_key = f"{now.date().isoformat()}:jummah"
        if today_key in self._last_actions:
            return []

        actions = []
        if 7 <= now.hour <= 12:
            actions.append({
                "type": "notification",
                "category": "jummah_reminder",
                "message": "Jummah Mubarak! Remember to read Surah Al-Kahf today.",
                "priority": "medium",
            })
            actions.append({
                "type": "led_scene",
                "action": "jummah_special",
                "color": "#FFD700",
                "brightness": 0.25,
                "animation": "gentle_shimmer",
            })
            self._last_actions[today_key] = now.isoformat()

        return actions

    # ------------------------------------------------------------------
    # Status & stats
    # ------------------------------------------------------------------

    def get_prayer_status(self, profile: dict) -> dict[str, Any]:
        self.ensure_shape(profile)
        try:
            prayers = self._prayer_service.get_today_prayers()
            next_prayer = self._prayer_service.get_next_prayer()
        except Exception:
            prayers = {}
            next_prayer = {}

        return {
            "today_prayers": prayers,
            "next_prayer": next_prayer,
            "prayer_mat_active": self._prayer_mat_active,
            "automation_enabled": profile.get("islamic", {}).get("prayer_automation_enabled", True),
            "stats": profile.get("islamic", {}).get("prayer_stats", {}),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _cleanup_old_actions(self, now: datetime) -> None:
        today = now.date().isoformat()
        self._last_actions = {
            k: v for k, v in self._last_actions.items()
            if k.startswith(today)
        }
