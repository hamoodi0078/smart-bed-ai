from __future__ import annotations

from dana.coach import DanaCoach
from dana.guide import DanaGuide
from dana.personality import DanaPersonality, PERSONALITY_CONFIGS, PersonalityConfig
from dana.therapist import DanaTherapist


class DanaCore:
    def __init__(
        self,
        personality: DanaPersonality = DanaPersonality.GUIDE,
        user_name: str = "Hamoud",
    ):
        self.personality = personality
        self.user_name = user_name
        self.coach = DanaCoach()
        self.guide = DanaGuide()
        self.therapist = DanaTherapist()

    def switch_personality(self, new_personality: DanaPersonality) -> str:
        self.personality = new_personality
        config = self.get_config()
        return f"Switched to {config.name} ({new_personality.value}) for {self.user_name}."

    def get_greeting(self) -> str:
        config = self.get_config()
        return f"Good evening {self.user_name}! {config.greeting}"

    def get_bedtime_message(self, hour: int) -> str:
        if self.personality == DanaPersonality.COACH:
            return self.coach.get_bedtime_message(hour)
        if self.personality == DanaPersonality.THERAPIST:
            return self.therapist.get_bedtime_message(hour)
        return self.guide.get_bedtime_message(hour)

    def get_config(self) -> PersonalityConfig:
        return PERSONALITY_CONFIGS[self.personality]

    def speak(self, message: str) -> None:
        print(f"[Dana {self.get_config().emoji}]: {message}")
