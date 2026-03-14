from __future__ import annotations


class GuestSettings:
    DEFAULT_GUEST_SCENE = {
        "led_color": "#F5F5DC",
        "brightness": 30,
        "audio": "none",
        "temperature": "neutral",
    }

    def get_guest_led_settings(self) -> dict:
        return dict(self.DEFAULT_GUEST_SCENE)

    def get_blocked_features(self) -> list[str]:
        return [
            "voice_memory",
            "personal_scenes",
            "sleep_tracking",
            "dana_personality",
            "islamic_reminders",
            "spotify_history",
            "automations",
        ]

    def get_allowed_features(self) -> list[str]:
        return [
            "basic_led_control",
            "brightness_control",
            "alarm",
            "manual_scene_select",
            "wind_down_basic",
        ]

    def get_guest_welcome_message(self) -> str:
        return "Welcome! You are using Guest Mode. Your privacy is protected — no data is stored during this session."

    def get_reset_message(self) -> str:
        return "Guest session ended. All temporary settings have been cleared. Welcome back!"
