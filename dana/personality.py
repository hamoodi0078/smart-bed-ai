from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DanaPersonality(str, Enum):
    COACH = "coach"
    GUIDE = "guide"
    THERAPIST = "therapist"


@dataclass(frozen=True)
class PersonalityConfig:
    name: str
    tagline: str
    tone: str
    emoji: str
    greeting: str
    sleep_message: str
    wake_message: str
    color_hex: str


PERSONALITY_CONFIGS = {
    DanaPersonality.COACH: PersonalityConfig(
        name="Dana Coach",
        tagline="Your sleep performance partner",
        tone="motivational, energetic, data-driven",
        emoji="💪",
        greeting="Let's crush your sleep goals tonight!",
        sleep_message="Time to recover and come back stronger tomorrow!",
        wake_message="Rise and shine champion! You slept {hours} hours. Let's review your performance!",
        color_hex="#FF6B35",
    ),
    DanaPersonality.GUIDE: PersonalityConfig(
        name="Dana Guide",
        tagline="Your gentle sleep companion",
        tone="calm, warm, spiritual, peaceful",
        emoji="🌙",
        greeting="Peace be with you. Let's prepare for a restful night.",
        sleep_message="May your sleep be peaceful and your dreams be beautiful.",
        wake_message="Good morning. You rested for {hours} hours. Take a moment of gratitude.",
        color_hex="#7B68EE",
    ),
    DanaPersonality.THERAPIST: PersonalityConfig(
        name="Dana Therapist",
        tagline="Your sleep wellness advisor",
        tone="professional, empathetic, analytical, supportive",
        emoji="🧠",
        greeting="How are you feeling tonight? Let's check in before sleep.",
        sleep_message="You've done well today. Let your mind rest and process.",
        wake_message="Good morning. Your body recovered for {hours} hours. How do you feel?",
        color_hex="#00D4FF",
    ),
}
