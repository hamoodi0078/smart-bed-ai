from __future__ import annotations

from enum import Enum


class NotificationType(str, Enum):
    PRAYER_REMINDER = "prayer_reminder"
    WIND_DOWN = "wind_down"
    MORNING_ALARM = "morning_alarm"
    SLEEP_REPORT = "sleep_report"
    STREAK_ACHIEVEMENT = "streak_achievement"
    DANA_CHECKIN = "dana_checkin"
    INACTIVITY_ALERT = "inactivity_alert"
    WEEKLY_REPORT = "weekly_report"
    RAMADAN_SUHOOR = "ramadan_suhoor"
    GUEST_MODE_RESET = "guest_mode_reset"


NOTIFICATION_TEMPLATES = {
    NotificationType.PRAYER_REMINDER: {
        "title": "🕌 Prayer Time",
        "body": "{prayer_name} prayer is in {minutes} minutes",
        "emoji": "🕌",
    },
    NotificationType.WIND_DOWN: {
        "title": "🌙 Time to Wind Down",
        "body": "Time to wind down, {user_name}. Let Dana guide you to sleep.",
        "emoji": "🌙",
    },
    NotificationType.MORNING_ALARM: {
        "title": "🌅 Good Morning",
        "body": "Rise and shine {user_name}! You slept {hours} hours.",
        "emoji": "🌅",
    },
    NotificationType.SLEEP_REPORT: {
        "title": "📊 Sleep Report Ready",
        "body": "Your weekly sleep report is ready!",
        "emoji": "📊",
    },
    NotificationType.STREAK_ACHIEVEMENT: {
        "title": "🏆 Achievement Unlocked!",
        "body": "{streak} night streak! MashaAllah {user_name}!",
        "emoji": "🏆",
    },
    NotificationType.DANA_CHECKIN: {
        "title": "💡 Dana Misses You",
        "body": "You haven't used Dana in {days} days — everything okay {user_name}?",
        "emoji": "💡",
    },
    NotificationType.INACTIVITY_ALERT: {
        "title": "💡 Still There?",
        "body": "You haven't used your smart bed in {days} days.",
        "emoji": "💡",
    },
    NotificationType.WEEKLY_REPORT: {
        "title": "📊 Weekly Sleep Report",
        "body": "Your weekly sleep wins are ready {user_name}!",
        "emoji": "📊",
    },
    NotificationType.RAMADAN_SUHOOR: {
        "title": "🌙 Suhoor Time",
        "body": "Suhoor is in {minutes} minutes. Wake up {user_name}.",
        "emoji": "🌙",
    },
    NotificationType.GUEST_MODE_RESET: {
        "title": "✅ Guest Session Ended",
        "body": "Guest mode reset. Welcome back {user_name}!",
        "emoji": "✅",
    },
}
