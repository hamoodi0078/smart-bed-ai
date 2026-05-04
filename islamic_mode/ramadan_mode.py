from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from islamic_mode.islamic_calendar import IslamicCalendarService
from islamic_mode.prayer_times import PrayerTimesService

logger = logging.getLogger("islamic_mode.ramadan_mode")


class RamadanMode:
    def __init__(
        self,
        calendar_service: IslamicCalendarService | None = None,
        prayer_service: PrayerTimesService | None = None,
    ):
        self.calendar_service = calendar_service or IslamicCalendarService()
        self.prayer_service = prayer_service or PrayerTimesService()
        self._last_actions: dict[str, str] = {}

    def is_active(self) -> bool:
        return self.calendar_service.is_ramadan()

    @staticmethod
    def _shift_time(time_text: str, minutes_delta: int) -> str:
        base = datetime.strptime(str(time_text), "%H:%M")
        shifted = base + timedelta(minutes=minutes_delta)
        return shifted.strftime("%H:%M")

    def get_suhoor_wake_time(self) -> str:
        fajr = self.prayer_service.get_today_prayers().get("Fajr", "")
        if not fajr:
            return ""
        return self._shift_time(fajr, -45)

    def get_iftar_time(self) -> str:
        return str(self.prayer_service.get_today_prayers().get("Maghrib", ""))

    def get_ramadan_greeting(self) -> str:
        return "رمضان كريم - Ramadan Kareem! May this blessed month bring you peace and joy."

    def get_tarawih_reminder(self) -> str:
        isha = self.prayer_service.get_today_prayers().get("Isha", "")
        if not isha:
            return "Tarawih reminder: 30 minutes after Isha is a beautiful time to stand in prayer tonight."
        tarawih_time = self._shift_time(isha, 30)
        return (
            f"Tarawih reminder: Around {tarawih_time}, take a few quiet moments for Tarawih prayer tonight."
        )

    # ------------------------------------------------------------------
    # Profile shape
    # ------------------------------------------------------------------

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("ramadan", {})
        ram = profile["ramadan"]
        ram.setdefault("fasting_log", [])
        ram.setdefault("suhoor_wake_enabled", True)
        ram.setdefault("iftar_alert_enabled", True)
        ram.setdefault("tarawih_reminder_enabled", True)
        ram.setdefault("laylatul_qadr_mode_enabled", True)
        ram.setdefault("daily_quran_goal_pages", 20)
        ram.setdefault("quran_pages_read_today", 0)
        ram.setdefault("quran_last_date", "")
        ram.setdefault("total_fasts_completed", 0)

    # ------------------------------------------------------------------
    # Full Ramadan automation evaluation
    # ------------------------------------------------------------------

    def evaluate(self, profile: dict, now: datetime | None = None) -> list[dict[str, Any]]:
        """Evaluate all Ramadan automations and return actions to execute."""
        now = now or datetime.now()
        self.ensure_shape(profile)

        if not self.is_active():
            return []

        actions: list[dict[str, Any]] = []
        today = now.date().isoformat()

        actions.extend(self._evaluate_suhoor(profile, now, today))
        actions.extend(self._evaluate_iftar(profile, now, today))
        actions.extend(self._evaluate_tarawih(profile, now, today))
        actions.extend(self._evaluate_laylatul_qadr(profile, now, today))
        actions.extend(self._evaluate_quran_reminder(profile, now, today))

        self._cleanup_old_actions(now)
        return actions

    # ------------------------------------------------------------------
    # Suhoor automation
    # ------------------------------------------------------------------

    def _evaluate_suhoor(self, profile: dict, now: datetime, today: str) -> list[dict[str, Any]]:
        ram = profile.get("ramadan", {})
        if not ram.get("suhoor_wake_enabled", True):
            return []

        suhoor_time = self.get_suhoor_wake_time()
        if not suhoor_time:
            return []

        try:
            sh, sm = [int(x) for x in suhoor_time.split(":")]
            suhoor_minutes = sh * 60 + sm
            now_minutes = now.hour * 60 + now.minute
            diff = suhoor_minutes - now_minutes
        except Exception:
            return []

        actions: list[dict[str, Any]] = []
        fajr = self.prayer_service.get_today_prayers().get("Fajr", "")

        key = f"{today}:suhoor_wake"
        if 0 <= diff <= 5 and key not in self._last_actions:
            self._last_actions[key] = now.isoformat()
            actions.append({
                "type": "led_scene",
                "action": "suhoor_wake",
                "color": "#FF8C00",
                "brightness": 0.20,
                "animation": "gentle_sunrise",
            })
            actions.append({
                "type": "voice",
                "message": f"Time for Suhoor. Fajr is at {fajr}. Eat well and make your intention.",
                "volume": 0.4,
            })
            actions.append({
                "type": "notification",
                "category": "ramadan_suhoor",
                "message": f"Suhoor time! Fajr at {fajr}.",
                "priority": "high",
            })

        return actions

    # ------------------------------------------------------------------
    # Iftar automation
    # ------------------------------------------------------------------

    def _evaluate_iftar(self, profile: dict, now: datetime, today: str) -> list[dict[str, Any]]:
        ram = profile.get("ramadan", {})
        if not ram.get("iftar_alert_enabled", True):
            return []

        iftar_time = self.get_iftar_time()
        if not iftar_time:
            return []

        try:
            ih, im = [int(x) for x in iftar_time.split(":")]
            iftar_minutes = ih * 60 + im
            now_minutes = now.hour * 60 + now.minute
            diff = iftar_minutes - now_minutes
        except Exception:
            return []

        actions: list[dict[str, Any]] = []

        pre_key = f"{today}:iftar_pre"
        if 5 < diff <= 10 and pre_key not in self._last_actions:
            self._last_actions[pre_key] = now.isoformat()
            actions.append({
                "type": "notification",
                "category": "ramadan_iftar_soon",
                "message": f"Iftar in {diff} minutes. Prepare to break your fast.",
                "priority": "medium",
            })

        at_key = f"{today}:iftar_at"
        if -2 <= diff <= 0 and at_key not in self._last_actions:
            self._last_actions[at_key] = now.isoformat()

            self._log_fast_completed(profile, today)

            actions.append({
                "type": "led_scene",
                "action": "iftar_celebration",
                "color": "#FFD700",
                "brightness": 0.40,
                "animation": "warm_glow",
            })
            actions.append({
                "type": "voice",
                "message": "Alhamdulillah, time to break your fast. Bismillah!",
                "volume": 0.5,
            })
            actions.append({
                "type": "notification",
                "category": "ramadan_iftar",
                "message": "Iftar time! Break your fast. Alhamdulillah.",
                "priority": "high",
            })

        return actions

    # ------------------------------------------------------------------
    # Tarawih reminder
    # ------------------------------------------------------------------

    def _evaluate_tarawih(self, profile: dict, now: datetime, today: str) -> list[dict[str, Any]]:
        ram = profile.get("ramadan", {})
        if not ram.get("tarawih_reminder_enabled", True):
            return []

        key = f"{today}:tarawih"
        if key in self._last_actions:
            return []

        isha = self.prayer_service.get_today_prayers().get("Isha", "")
        if not isha:
            return []

        try:
            tarawih_time = self._shift_time(isha, 30)
            th, tm = [int(x) for x in tarawih_time.split(":")]
            tarawih_minutes = th * 60 + tm
            now_minutes = now.hour * 60 + now.minute
            diff = tarawih_minutes - now_minutes
        except Exception:
            return []

        if 0 <= diff <= 5:
            self._last_actions[key] = now.isoformat()
            return [{
                "type": "notification",
                "category": "ramadan_tarawih",
                "message": self.get_tarawih_reminder(),
                "priority": "medium",
            }]

        return []

    # ------------------------------------------------------------------
    # Laylatul Qadr (last 10 nights)
    # ------------------------------------------------------------------

    def _evaluate_laylatul_qadr(self, profile: dict, now: datetime, today: str) -> list[dict[str, Any]]:
        ram = profile.get("ramadan", {})
        if not ram.get("laylatul_qadr_mode_enabled", True):
            return []

        key = f"{today}:laylatul_qadr"
        if key in self._last_actions:
            return []

        try:
            hijri = self.calendar_service.get_hijri_date()
            hijri_text = str(hijri.get("hijri_date", "")).strip()
            parts = hijri_text.split()
            if len(parts) >= 1:
                day_num = int(parts[0])
            else:
                return []
            month = str(hijri.get("hijri_month", "")).strip().lower()
        except Exception:
            return []

        if month not in {"ramadan", "ramadhan"} or day_num < 21:
            return []

        is_odd = day_num % 2 == 1
        actions: list[dict[str, Any]] = []

        if 20 <= now.hour <= 23:
            self._last_actions[key] = now.isoformat()
            night_label = f"night {day_num}"
            if is_odd:
                actions.append({
                    "type": "led_scene",
                    "action": "laylatul_qadr_special",
                    "color": "#E6E6FA",
                    "brightness": 0.15,
                    "animation": "starlight_shimmer",
                })
                actions.append({
                    "type": "notification",
                    "category": "laylatul_qadr",
                    "message": f"This is {night_label} of Ramadan (odd night). Seek Laylatul Qadr with extra worship tonight.",
                    "priority": "high",
                })
            else:
                actions.append({
                    "type": "notification",
                    "category": "last_ten_nights",
                    "message": f"Last 10 nights: {night_label}. Increase your ibadah and dua tonight.",
                    "priority": "medium",
                })

        return actions

    # ------------------------------------------------------------------
    # Quran reading reminder
    # ------------------------------------------------------------------

    def _evaluate_quran_reminder(self, profile: dict, now: datetime, today: str) -> list[dict[str, Any]]:
        ram = profile.get("ramadan", {})
        goal = int(ram.get("daily_quran_goal_pages", 20) or 20)
        if goal <= 0:
            return []

        key = f"{today}:quran_reminder"
        if key in self._last_actions:
            return []

        if ram.get("quran_last_date", "") == today:
            pages_read = int(ram.get("quran_pages_read_today", 0) or 0)
            if pages_read >= goal:
                return []

        if 14 <= now.hour <= 17:
            self._last_actions[key] = now.isoformat()
            pages_read = int(ram.get("quran_pages_read_today", 0) or 0) if ram.get("quran_last_date", "") == today else 0
            remaining = max(0, goal - pages_read)
            return [{
                "type": "notification",
                "category": "ramadan_quran",
                "message": f"Quran reminder: {remaining} pages remaining to meet today's goal of {goal} pages.",
                "priority": "low",
            }]

        return []

    # ------------------------------------------------------------------
    # Fasting log & progress
    # ------------------------------------------------------------------

    def _log_fast_completed(self, profile: dict, today: str) -> None:
        ram = profile.get("ramadan", {})
        log = ram.get("fasting_log", [])
        if any(str(e.get("date", "")) == today for e in log):
            return
        log.append({"date": today, "completed": True})
        ram["fasting_log"] = log[-40:]
        ram["total_fasts_completed"] = sum(1 for e in log if e.get("completed", False))

    def log_quran_pages(self, profile: dict, pages: int, now: datetime | None = None) -> dict[str, Any]:
        """Log Quran pages read today."""
        now = now or datetime.now()
        self.ensure_shape(profile)
        ram = profile["ramadan"]
        today = now.date().isoformat()

        if ram.get("quran_last_date", "") != today:
            ram["quran_pages_read_today"] = 0
            ram["quran_last_date"] = today

        ram["quran_pages_read_today"] = int(ram.get("quran_pages_read_today", 0)) + max(0, int(pages))
        goal = int(ram.get("daily_quran_goal_pages", 20) or 20)
        current = int(ram.get("quran_pages_read_today", 0))

        return {
            "pages_today": current,
            "goal": goal,
            "remaining": max(0, goal - current),
            "completed": current >= goal,
            "message": f"{current}/{goal} pages today." + (" MashaAllah, goal reached!" if current >= goal else ""),
        }

    def get_ramadan_progress(self, profile: dict) -> dict[str, Any]:
        """Return Ramadan progress summary."""
        self.ensure_shape(profile)
        ram = profile.get("ramadan", {})
        log = ram.get("fasting_log", [])
        completed = sum(1 for e in log if e.get("completed", False))

        try:
            hijri = self.calendar_service.get_hijri_date()
            hijri_text = str(hijri.get("hijri_date", "")).strip()
            parts = hijri_text.split()
            day_num = int(parts[0]) if parts else 0
        except Exception:
            day_num = 0

        return {
            "is_ramadan": self.is_active(),
            "current_day": day_num,
            "fasts_completed": completed,
            "total_days": 30,
            "progress_pct": round(completed / 30 * 100, 1),
            "quran_pages_today": int(ram.get("quran_pages_read_today", 0)),
            "quran_goal": int(ram.get("daily_quran_goal_pages", 20)),
            "suhoor_time": self.get_suhoor_wake_time(),
            "iftar_time": self.get_iftar_time(),
            "message": f"Day {day_num}/30 — {completed} fasts completed. Alhamdulillah!",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _cleanup_old_actions(self, now: datetime) -> None:
        today = now.date().isoformat()
        self._last_actions = {k: v for k, v in self._last_actions.items() if k.startswith(today)}
