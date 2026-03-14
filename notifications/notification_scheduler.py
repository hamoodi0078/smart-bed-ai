from __future__ import annotations

import datetime
import json
import os

from notifications.expo_sender import ExpoPushSender
from notifications.notification_types import NotificationType
from notifications.whatsapp_notifier import WhatsAppNotifier


class NotificationScheduler:
    def __init__(self, expo_sender: ExpoPushSender, whatsapp_notifier: WhatsAppNotifier):
        self.expo_sender = expo_sender
        self.whatsapp_notifier = whatsapp_notifier
        self.scheduled_path = os.path.join(os.path.dirname(__file__), "scheduled.json")

    def _read_scheduled(self) -> dict:
        if not os.path.exists(self.scheduled_path):
            return {}
        try:
            with open(self.scheduled_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_scheduled(self, payload: dict) -> None:
        os.makedirs(os.path.dirname(self.scheduled_path), exist_ok=True)
        with open(self.scheduled_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)

    def schedule_wind_down(self, user_id: str, hour: int = 21, minute: int = 0) -> dict:
        scheduled = self._read_scheduled()
        user_key = str(user_id)
        user_entry = scheduled.get(user_key, {}) if isinstance(scheduled.get(user_key, {}), dict) else {}
        user_entry["wind_down"] = {
            "hour": int(hour),
            "minute": int(minute),
            "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        scheduled[user_key] = user_entry
        self._write_scheduled(scheduled)
        return user_entry["wind_down"]

    def schedule_alarm(self, user_id: str, hour: int, minute: int) -> dict:
        scheduled = self._read_scheduled()
        user_key = str(user_id)
        user_entry = scheduled.get(user_key, {}) if isinstance(scheduled.get(user_key, {}), dict) else {}
        user_entry["alarm"] = {
            "hour": int(hour),
            "minute": int(minute),
            "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        scheduled[user_key] = user_entry
        self._write_scheduled(scheduled)
        return user_entry["alarm"]

    def check_inactivity(self, user_id: str, last_active_date: str, threshold_days: int = 3) -> dict:
        try:
            last_active = datetime.datetime.fromisoformat(str(last_active_date)).date()
        except ValueError:
            try:
                last_active = datetime.date.fromisoformat(str(last_active_date))
            except ValueError:
                return {"triggered": False, "error": "Invalid last_active_date format."}

        days_inactive = (datetime.date.today() - last_active).days
        if days_inactive < int(threshold_days):
            return {"triggered": False, "days_inactive": days_inactive}

        expo_result = self.expo_sender.send_to_user(
            user_id=user_id,
            notification_type=NotificationType.DANA_CHECKIN,
            template_vars={"days": days_inactive, "user_name": str(user_id)},
        )

        scheduled = self._read_scheduled()
        phone = ""
        user_entry = scheduled.get(str(user_id), {})
        if isinstance(user_entry, dict):
            phone = str(user_entry.get("phone", "")).strip()
        whatsapp_result = (
            self.whatsapp_notifier.send_dana_checkin(phone, str(user_id), days_inactive)
            if phone
            else {"sent": False, "reason": "phone_not_provided"}
        )
        return {
            "triggered": True,
            "days_inactive": days_inactive,
            "expo": expo_result,
            "whatsapp": whatsapp_result,
        }

    def check_streak(self, user_id: str, streak_days: int, phone: str = None) -> dict:
        milestones = {1, 3, 7, 14, 30}
        streak_value = int(streak_days)
        if streak_value not in milestones:
            return {"triggered": False, "streak_days": streak_value}

        expo_result = self.expo_sender.send_to_user(
            user_id=user_id,
            notification_type=NotificationType.STREAK_ACHIEVEMENT,
            template_vars={"streak": streak_value, "user_name": str(user_id)},
        )
        whatsapp_result = (
            self.whatsapp_notifier.send_streak_message(phone, str(user_id), streak_value)
            if phone
            else {"sent": False, "reason": "phone_not_provided"}
        )
        return {
            "triggered": True,
            "streak_days": streak_value,
            "expo": expo_result,
            "whatsapp": whatsapp_result,
        }

    def send_weekly_report_notification(self, user_id: str) -> dict:
        return self.expo_sender.send_to_user(
            user_id=user_id,
            notification_type=NotificationType.WEEKLY_REPORT,
            template_vars={"user_name": str(user_id)},
        )

    def get_scheduled(self, user_id: str) -> dict:
        scheduled = self._read_scheduled()
        entry = scheduled.get(str(user_id), {})
        return entry if isinstance(entry, dict) else {}
