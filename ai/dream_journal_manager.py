from datetime import datetime
from typing import Dict, List, Tuple

from ai.emotion_router import detect_dream_emotion


class DreamJournalManager:
    """Morning dream prompt + lightweight dream insights."""

    def __init__(self):
        self.is_prompting = False

    def ensure_profile_shape(self, profile: dict):
        profile.setdefault("dream_journal", {})
        journal = profile["dream_journal"]
        journal.setdefault("enabled", True)
        journal.setdefault("last_prompt_date", "")
        journal.setdefault("entries", [])
        journal.setdefault("mood_summary", {"total_entries": 0})
        journal.setdefault("theme_summary", {})

    def should_prompt_dream(self, profile: dict, now: datetime = None) -> bool:
        self.ensure_profile_shape(profile)
        now = now or datetime.now()
        if not profile["dream_journal"].get("enabled", True):
            return False
        if not (6 <= now.hour <= 11):
            return False
        return profile["dream_journal"].get("last_prompt_date", "") != now.date().isoformat()

    def start_dream_prompt_session(self, profile: dict, stt_manager, tts_manager, audio_player) -> str:
        self.ensure_profile_shape(profile)
        self.is_prompting = True
        profile["dream_journal"]["last_prompt_date"] = datetime.now().date().isoformat()
        return "Good morning. What did you dream?"

    def capture_dream_response(self, user_text: str, profile: dict) -> Tuple[str, Dict]:
        self.ensure_profile_shape(profile)
        text = (user_text or "").strip()
        if not text:
            return "I did not catch the dream details. Try again in one sentence.", {}

        mood = detect_dream_emotion(text)
        themes = self._extract_themes(text)
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "text": text,
            "mood": mood,
            "themes": themes,
        }
        profile["dream_journal"]["entries"].append(entry)
        profile["dream_journal"]["entries"] = profile["dream_journal"]["entries"][-100:]

        self._update_mood_summary(profile, mood)
        self._update_theme_summary(profile, themes)
        self.is_prompting = False

        return self._followup_message(mood, themes), entry

    def _extract_themes(self, text: str) -> List[str]:
        lower = text.lower()
        theme_keywords = {
            "water": ["water", "ocean", "sea", "river", "rain"],
            "flight": ["fly", "flying", "sky", "floating"],
            "chase": ["chase", "running", "escape", "pursuit"],
            "people": ["friend", "family", "mother", "father", "someone"],
            "school_work": ["school", "exam", "class", "work", "office"],
            "animals": ["animal", "dog", "cat", "snake", "bird"],
        }
        out = []
        for theme, kws in theme_keywords.items():
            if any(k in lower for k in kws):
                out.append(theme)
        return out

    def _update_mood_summary(self, profile: dict, mood: str):
        summary = profile["dream_journal"]["mood_summary"]
        summary[mood] = int(summary.get(mood, 0)) + 1
        summary["total_entries"] = int(summary.get("total_entries", 0)) + 1

    def _update_theme_summary(self, profile: dict, themes: List[str]):
        summary = profile["dream_journal"]["theme_summary"]
        for theme in themes:
            summary[theme] = int(summary.get(theme, 0)) + 1

    def _followup_message(self, mood: str, themes: List[str]) -> str:
        if mood in ("dream_negative", "distressed"):
            return "Thanks for sharing. That sounds intense. Let us do a calm start to the morning."
        if mood in ("dream_positive", "motivated"):
            return "Thanks for sharing. That sounds uplifting."
        if themes:
            return f"Dream saved. I noticed themes: {', '.join(themes[:2])}."
        return "Dream saved."

    def get_dream_insights(self, profile: dict) -> str:
        self.ensure_profile_shape(profile)
        entries = profile["dream_journal"].get("entries", [])
        if not entries:
            return "No dream journal entries yet."

        mood_summary = profile["dream_journal"].get("mood_summary", {})
        theme_summary = profile["dream_journal"].get("theme_summary", {})
        total = int(mood_summary.get("total_entries", 0))
        if total <= 0:
            total = len(entries)

        dominant_mood = "neutral"
        top_count = -1
        for mood, count in mood_summary.items():
            if mood == "total_entries":
                continue
            if int(count) > top_count:
                dominant_mood = mood
                top_count = int(count)

        top_themes = sorted(theme_summary.items(), key=lambda kv: kv[1], reverse=True)[:2]
        if top_themes:
            themes_text = ", ".join(t for t, _ in top_themes)
            return f"Dream insights: {len(entries)} entries, dominant mood {dominant_mood}, common themes {themes_text}."
        return f"Dream insights: {len(entries)} entries, dominant mood {dominant_mood}."

    def set_dream_prompt_enabled(self, profile: dict, enabled: bool) -> str:
        self.ensure_profile_shape(profile)
        profile["dream_journal"]["enabled"] = bool(enabled)
        return f"Dream journal {'enabled' if enabled else 'disabled'}."
