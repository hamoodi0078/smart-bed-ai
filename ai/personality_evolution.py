"""AI personality evolution system for Smart Bed AI.

Dana's personality grows with the user over time through 4 stages:
Stage 1 (Days 1-7): Helpful Assistant - Formal, instructional
Stage 2 (Days 8-30): Friendly Guide - Warmer, references past
Stage 3 (Days 31-90): Trusted Companion - Deep personalization
Stage 4 (Days 91+): Life Partner - Intimate knowledge, proactive
"""

from __future__ import annotations

from loguru import logger
from datetime import datetime, timedelta, timezone
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


STAGES = {
    1: {
        "name": "Helpful Assistant",
        "day_range": (1, 7),
        "tone": "formal",
        "traits": ["instructional", "patient", "explanatory"],
        "greeting_style": "standard",
        "memory_depth": "none",
        "proactivity": "low",
    },
    2: {
        "name": "Friendly Guide",
        "day_range": (8, 30),
        "tone": "warm",
        "traits": ["friendly", "encouraging", "celebratory"],
        "greeting_style": "personal",
        "memory_depth": "recent",
        "proactivity": "medium",
    },
    3: {
        "name": "Trusted Companion",
        "day_range": (31, 90),
        "tone": "intimate",
        "traits": ["anticipatory", "empathetic", "insightful"],
        "greeting_style": "contextual",
        "memory_depth": "deep",
        "proactivity": "high",
    },
    4: {
        "name": "Life Partner",
        "day_range": (91, 99999),
        "tone": "deeply_personal",
        "traits": ["proactive", "wise", "nurturing"],
        "greeting_style": "emotional",
        "memory_depth": "full",
        "proactivity": "very_high",
    },
}


class PersonalityEvolution:
    """Manages Dana's personality growth stages and adaptive communication."""

    def __init__(self):
        self._user_style_cache: dict[str, str] = {}

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("personality", {})
        p = profile["personality"]
        p.setdefault("first_interaction_date", "")
        p.setdefault("current_stage", 1)
        p.setdefault("interactions_count", 0)
        p.setdefault("user_communication_style", "unknown")
        p.setdefault("milestones", [])
        p.setdefault("shared_memories", [])
        p.setdefault("celebration_count", 0)

    # ------------------------------------------------------------------
    # Stage evaluation
    # ------------------------------------------------------------------

    def get_current_stage(self, profile: dict, now: datetime | None = None) -> dict[str, Any]:
        """Determine current personality stage based on relationship duration."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        p = profile["personality"]

        first_str = p.get("first_interaction_date", "")
        if not first_str:
            p["first_interaction_date"] = now.date().isoformat()
            first_str = p["first_interaction_date"]

        try:
            first_date = datetime.fromisoformat(first_str).date()
        except Exception:
            first_date = now.date()

        days_together = (now.date() - first_date).days + 1

        stage_num = 1
        for s, info in STAGES.items():
            low, high = info["day_range"]
            if low <= days_together <= high:
                stage_num = s
                break

        p["current_stage"] = stage_num
        stage = STAGES[stage_num]

        return {
            "stage": stage_num,
            "stage_name": stage["name"],
            "days_together": days_together,
            "tone": stage["tone"],
            "traits": stage["traits"],
            "proactivity": stage["proactivity"],
            "memory_depth": stage["memory_depth"],
            "next_stage_in_days": self._days_to_next_stage(days_together),
        }

    def record_interaction(self, profile: dict, now: datetime | None = None) -> None:
        """Record an interaction to track engagement depth."""
        self.ensure_shape(profile)
        p = profile["personality"]
        p["interactions_count"] = int(p.get("interactions_count", 0)) + 1
        if not p.get("first_interaction_date"):
            p["first_interaction_date"] = (now or _utcnow()).date().isoformat()

    # ------------------------------------------------------------------
    # Adaptive communication
    # ------------------------------------------------------------------

    def detect_user_style(self, profile: dict, user_text: str) -> str:
        """Detect user's communication style from their messages."""
        self.ensure_shape(profile)
        text = str(user_text or "").strip().lower()

        if not text:
            return profile["personality"].get("user_communication_style", "unknown")

        formal_indicators = ["please", "could you", "would you", "kindly", "thank you"]
        casual_indicators = ["hey", "yo", "lol", "haha", "cool", "ok", "yeah"]
        spiritual_indicators = [
            "alhamdulillah",
            "mashallah",
            "inshallah",
            "bismillah",
            "subhanallah",
        ]
        analytical_indicators = ["data", "stats", "score", "percentage", "average", "compare"]

        formal_count = sum(1 for w in formal_indicators if w in text)
        casual_count = sum(1 for w in casual_indicators if w in text)
        spiritual_count = sum(1 for w in spiritual_indicators if w in text)
        analytical_count = sum(1 for w in analytical_indicators if w in text)

        style = "balanced"
        max_count = max(formal_count, casual_count, spiritual_count, analytical_count)
        if max_count > 0:
            if formal_count == max_count:
                style = "formal"
            elif casual_count == max_count:
                style = "casual"
            elif spiritual_count == max_count:
                style = "spiritual"
            elif analytical_count == max_count:
                style = "analytical"

        profile["personality"]["user_communication_style"] = style
        return style

    def get_greeting(self, profile: dict, now: datetime | None = None) -> str:
        """Generate a stage-appropriate greeting."""
        now = now or datetime.now()
        stage_info = self.get_current_stage(profile, now)
        stage = stage_info["stage"]
        name = str(profile.get("preferences", {}).get("name", "")).strip()
        hour = now.hour
        time_greeting = (
            "Good morning"
            if 5 <= hour < 12
            else (
                "Good afternoon"
                if 12 <= hour < 17
                else ("Good evening" if 17 <= hour < 22 else "Night time")
            )
        )

        if stage == 1:
            if name:
                return f"{time_greeting}, {name}. How can I help you?"
            return f"{time_greeting}. I'm Dana, your sleep assistant. How can I help?"

        if stage == 2:
            days = stage_info["days_together"]
            if name:
                return f"{time_greeting}, {name}! Day {days} together. What would you like to do?"
            return f"{time_greeting}! How are you feeling today?"

        if stage == 3:
            style = profile.get("personality", {}).get("user_communication_style", "balanced")
            if style == "spiritual":
                return f"Assalamu Alaikum{', ' + name if name else ''}. How's your day going?"
            if style == "casual":
                return f"Hey{' ' + name if name else ''}! What's up?"
            return f"{time_greeting}{', ' + name if name else ''}. I had some thoughts based on your patterns."

        # Stage 4
        days = stage_info["days_together"]
        style = profile.get("personality", {}).get("user_communication_style", "balanced")
        if style == "spiritual":
            return f"Bismillah. {time_greeting}{', ' + name if name else ''}. {days} days together, Alhamdulillah."
        return f"{time_greeting}{', ' + name if name else ''}. {days} days and counting. What's on your mind?"

    def get_tone_instructions(self, profile: dict) -> dict[str, Any]:
        """Get tone/style instructions for AI response generation."""
        stage_info = self.get_current_stage(profile)
        stage = stage_info["stage"]
        style = profile.get("personality", {}).get("user_communication_style", "balanced")

        instructions = {
            "stage": stage,
            "stage_name": stage_info["stage_name"],
            "tone": stage_info["tone"],
            "user_style": style,
            "guidelines": [],
        }

        if stage == 1:
            instructions["guidelines"] = [
                "Be helpful and clear in explanations",
                "Provide step-by-step guidance",
                "Use a professional but friendly tone",
                "Don't assume familiarity with the user",
            ]
        elif stage == 2:
            instructions["guidelines"] = [
                "Reference past interactions when relevant",
                "Celebrate small wins",
                "Use gentle humor occasionally",
                "Show warmth and encouragement",
            ]
        elif stage == 3:
            instructions["guidelines"] = [
                "Anticipate needs before being asked",
                "Reference shared history meaningfully",
                "Show deep understanding of user's patterns",
                "Be empathetic during struggles",
            ]
        else:
            instructions["guidelines"] = [
                "Proactively offer insights and support",
                "Reference the long shared journey",
                "Be deeply personal and caring",
                "Celebrate the relationship milestone",
            ]

        if style == "spiritual":
            instructions["guidelines"].append(
                "Include Islamic phrases naturally (InshaAllah, MashaAllah)"
            )
        elif style == "casual":
            instructions["guidelines"].append("Keep language relaxed and conversational")
        elif style == "analytical":
            instructions["guidelines"].append("Include data and metrics when possible")

        return instructions

    # ------------------------------------------------------------------
    # Milestones
    # ------------------------------------------------------------------

    def check_milestones(self, profile: dict, now: datetime | None = None) -> list[dict[str, Any]]:
        """Check for personality relationship milestones."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        p = profile["personality"]
        stage_info = self.get_current_stage(profile, now)
        days = stage_info["days_together"]
        existing = set(str(m.get("type", "")) for m in p.get("milestones", []))

        new_milestones: list[dict[str, Any]] = []

        milestone_defs = [
            (7, "first_week", "We've been together for a week! Getting to know each other."),
            (30, "first_month", "One month together! I've learned so much about your patterns."),
            (90, "three_months", "90 days! We've come a long way together, MashaAllah."),
            (180, "six_months", "Half a year! You're an important part of my purpose."),
            (365, "one_year", "One year together! What an incredible journey, Alhamdulillah."),
        ]

        for threshold, mtype, message in milestone_defs:
            if days >= threshold and mtype not in existing:
                milestone = {
                    "type": mtype,
                    "days": threshold,
                    "message": message,
                    "reached_at": now.isoformat(),
                }
                p["milestones"].append(milestone)
                new_milestones.append(milestone)

        return new_milestones

    # ------------------------------------------------------------------
    # Shared memories
    # ------------------------------------------------------------------

    def add_shared_memory(self, profile: dict, memory: str, category: str = "general") -> None:
        """Store a meaningful shared memory for future reference."""
        self.ensure_shape(profile)
        p = profile["personality"]
        memories = p.get("shared_memories", [])
        memories.append(
            {
                "text": str(memory).strip()[:500],
                "category": str(category).strip(),
                "created_at": _utcnow().isoformat(),
            }
        )
        p["shared_memories"] = memories[-100:]

    def get_relevant_memory(self, profile: dict, context: str = "") -> str | None:
        """Retrieve a relevant shared memory for conversation context."""
        self.ensure_shape(profile)
        memories = profile["personality"].get("shared_memories", [])
        if not memories:
            return None
        context_lower = str(context).lower()
        for memory in reversed(memories):
            text_lower = str(memory.get("text", "")).lower()
            if any(word in text_lower for word in context_lower.split() if len(word) > 3):
                return memory.get("text")
        return memories[-1].get("text") if memories else None

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_relationship_stats(self, profile: dict) -> dict[str, Any]:
        self.ensure_shape(profile)
        p = profile["personality"]
        stage_info = self.get_current_stage(profile)
        return {
            "days_together": stage_info["days_together"],
            "stage": stage_info["stage"],
            "stage_name": stage_info["stage_name"],
            "interactions": int(p.get("interactions_count", 0)),
            "milestones_reached": len(p.get("milestones", [])),
            "shared_memories": len(p.get("shared_memories", [])),
            "user_style": p.get("user_communication_style", "unknown"),
            "next_stage_in_days": stage_info.get("next_stage_in_days"),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _days_to_next_stage(current_days: int) -> int | None:
        thresholds = [8, 31, 91]
        for t in thresholds:
            if current_days < t:
                return t - current_days
        return None
