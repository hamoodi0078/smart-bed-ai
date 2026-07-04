from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from whatsapp_client import send_whatsapp_message
except Exception:
    try:
        from whatsapp_client import send_hello_world as _send_hello_world
    except Exception:
        _send_hello_world = None

    def send_whatsapp_message(phone: str, message: str):
        if _send_hello_world is None:
            raise RuntimeError("No WhatsApp sender function is available.")
        return _send_hello_world(phone)


class WhatsAppNotifier:
    def _send(self, phone: str, message: str) -> dict:
        try:
            response = send_whatsapp_message(phone, message)
            return {"sent": True, "response": response}
        except Exception as exc:
            return {"sent": False, "error": str(exc)}

    def send_prayer_reminder(self, phone: str, prayer_name: str, minutes: int) -> dict:
        message = f"🕌 {prayer_name} prayer is in {minutes} minutes. \n\nاللَّهُمَّ أَعِنِّي عَلَى ذِكْرِكَ"
        return self._send(phone, message)

    def send_wind_down_reminder(self, phone: str, user_name: str) -> dict:
        message = f"🌙 Time to wind down {user_name}. Your smart bed is ready."
        return self._send(phone, message)

    def send_streak_message(self, phone: str, user_name: str, streak: int) -> dict:
        message = f"🏆 MashaAllah {user_name}! {streak} night streak! Keep it up!"
        return self._send(phone, message)

    def send_morning_message(self, phone: str, user_name: str, hours: float) -> dict:
        message = f"🌅 Good morning {user_name}! You slept {hours} hours. Have a blessed day!"
        return self._send(phone, message)

    def send_suhoor_reminder(self, phone: str, user_name: str, minutes: int) -> dict:
        message = f"🌙 Suhoor reminder: {minutes} minutes remaining {user_name}. Ramadan Kareem!"
        return self._send(phone, message)

    def send_dana_checkin(self, phone: str, user_name: str, days: int) -> dict:
        message = f"💡 Dana check-in: You have been away for {days} days {user_name}. We miss you."
        return self._send(phone, message)
