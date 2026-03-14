from __future__ import annotations

from datetime import datetime


class DanaGuide:
    def get_bedtime_message(self, hour: int) -> str:
        if hour < 21:
            return "A peaceful early night is a gift to your body and heart."
        if hour < 23:
            return "This is a beautiful time to settle in and rest deeply."
        if hour < 24:
            return "Take a soft breath and let the day gently fade."
        return "It's late. Let's quiet the mind and welcome calm sleep now."

    def get_wind_down_message(self, step: int) -> str:
        steps = {
            1: "Begin with three deep breaths. In through the nose, out through the mouth.",
            2: "Feel the lights softening around you. Let your body relax.",
            3: "The sounds of nature surround you. Release the day.",
            4: "You are safe and peaceful. Drift gently into sleep.",
        }
        return steps.get(step, "Stay present with your breath and let your body unwind.")

    def get_prayer_message(self, prayer_name: str) -> str:
        return (
            f"It is almost time for {prayer_name}. "
            "A moment of peace and connection."
        )

    def get_islamic_good_night(self) -> str:
        return "بِسْمِكَ اللَّهُمَّ أَمُوتُ وَأَحْيَا — In Your name O Allah, I die and I live. Sleep well."

    def get_gratitude_prompt(self) -> str:
        prompts = [
            "What is one blessing from today that made your heart lighter?",
            "Who supported you today, and how can you thank them?",
            "What challenge did Allah help you through today?",
            "What small moment of peace are you grateful for tonight?",
            "What did your body do for you today that you appreciate?",
            "What lesson from today are you thankful to carry forward?",
            "What is one dua you feel grateful Allah answered, even quietly?",
        ]
        return prompts[datetime.today().weekday() % len(prompts)]
