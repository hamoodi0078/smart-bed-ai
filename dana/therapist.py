from __future__ import annotations

from datetime import datetime


class DanaTherapist:
    def get_checkin_questions(self) -> list[str]:
        return [
            "How was your stress level today? (1-10)",
            "Did anything worry you today?",
            "What was one good thing that happened today?",
        ]

    def get_stress_response(self, stress_level: int) -> str:
        if 1 <= stress_level <= 3:
            return "You had a calm day. Your sleep should come easily."
        if 4 <= stress_level <= 6:
            return "Moderate stress detected. I recommend the breathing exercise tonight."
        return "High stress today. Let's start with a longer wind-down and breathing focus."

    def get_followup_message(self, previous_sleep_score: int) -> str:
        if previous_sleep_score >= 85:
            return "You slept well last night. Let's reinforce what worked so it stays consistent."
        if previous_sleep_score >= 65:
            return (
                "Last night was moderate. With a small adjustment tonight, your sleep can improve."
            )
        return "Last night looked difficult. Let's be gentle and focus on safety, calm, and recovery tonight."

    def get_pattern_insight(self, bad_nights_this_week: int) -> str:
        if bad_nights_this_week >= 3:
            return "I've noticed a pattern of difficult sleep this week. Let's talk about what might be affecting you."
        return "Your sleep patterns look healthy this week. Keep up your routine."

    def get_affirmation(self) -> str:
        affirmations = [
            "I release today and allow myself to rest without guilt.",
            "My body knows how to recover, and I trust that process.",
            "I can let go of what I cannot control tonight.",
            "Rest is productive, and I deserve it.",
            "I am safe in this moment, and calm is available to me.",
            "Each night is a new opportunity to heal and reset.",
            "Small consistent steps are enough; I am making progress.",
        ]
        return affirmations[datetime.today().weekday() % len(affirmations)]

    def get_bedtime_message(self, hour: int) -> str:
        if hour < 22:
            return "You're giving your nervous system a strong start tonight. Let's keep this gentle rhythm."
        if hour < 24:
            return "This is a healthy window for sleep. Take a slow breath and settle in."
        return "It's late, so let's simplify everything and focus on calm rest now."
