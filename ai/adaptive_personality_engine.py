from datetime import datetime


class AdaptivePersonalityEngine:
    """Selects therapist/coach/guide style per turn based on context."""

    def ensure_profile_shape(self, profile: dict):
        profile.setdefault("adaptive_personality", {})
        ap = profile["adaptive_personality"]
        ap.setdefault("enabled", True)
        ap.setdefault("manual_override", "")
        ap.setdefault("history", [])
        ap.setdefault("last_selected", "")

    def choose_personality(
        self, profile: dict, emotion_state: str, now: datetime = None
    ) -> tuple[str, float, str]:
        self.ensure_profile_shape(profile)
        ap = profile["adaptive_personality"]

        manual = str(ap.get("manual_override", "")).strip().lower()
        if manual in ("therapist", "coach", "guide"):
            ap["last_selected"] = manual
            return manual, 1.0, "manual_override"

        if not bool(ap.get("enabled", True)):
            base = profile.get("preferences", {}).get("personality", "therapist")
            return str(base), 0.5, "disabled"

        hour = (now or datetime.now()).hour
        emotion = (emotion_state or "neutral").lower().strip()

        if emotion in ("distressed", "low_energy"):
            chosen = "therapist"
            confidence = 0.9
            reason = "emotion_support"
        elif emotion == "motivated":
            chosen = "coach"
            confidence = 0.85
            reason = "momentum"
        elif 6 <= hour <= 11:
            chosen = "coach"
            confidence = 0.7
            reason = "morning_activation"
        elif hour >= 21 or hour <= 5:
            chosen = "therapist"
            confidence = 0.7
            reason = "night_calm"
        else:
            chosen = "guide"
            confidence = 0.6
            reason = "balanced"

        ap["last_selected"] = chosen
        return chosen, confidence, reason

    def record_interaction(
        self, profile: dict, personality: str, emotion_state: str, user_text: str, score=None
    ):
        self.ensure_profile_shape(profile)
        hist = profile["adaptive_personality"]["history"]
        hist.append(
            {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "personality": (personality or "").strip(),
                "emotion": (emotion_state or "neutral").strip(),
                "score": score,
                "sample": (user_text or "")[:100],
            }
        )
        profile["adaptive_personality"]["history"] = hist[-150:]

    def set_adaptive_enabled(self, profile: dict, enabled: bool) -> str:
        self.ensure_profile_shape(profile)
        profile["adaptive_personality"]["enabled"] = bool(enabled)
        return f"Adaptive personality {'enabled' if enabled else 'disabled'}."

    def set_manual_override(self, profile: dict, personality: str) -> str:
        self.ensure_profile_shape(profile)
        p = (personality or "").strip().lower()
        if p not in ("therapist", "coach", "guide"):
            return "Choose therapist, coach, or guide."
        profile["adaptive_personality"]["manual_override"] = p
        return f"Manual personality override set to {p}."

    def clear_manual_override(self, profile: dict) -> str:
        self.ensure_profile_shape(profile)
        profile["adaptive_personality"]["manual_override"] = ""
        return "Manual personality override cleared."

    def get_personality_insights(self, profile: dict) -> str:
        self.ensure_profile_shape(profile)
        ap = profile["adaptive_personality"]
        history = ap.get("history", [])
        if not history:
            return "Adaptive personality is active. No interaction history yet."

        counts = {"therapist": 0, "coach": 0, "guide": 0}
        for item in history[-30:]:
            p = str(item.get("personality", "")).lower().strip()
            if p in counts:
                counts[p] += 1

        max_count = max(counts.values())
        if max_count == 0:
            return "Adaptive personality insights: no classified style usage in recent interactions yet."

        leaders = [name for name, value in counts.items() if value == max_count]
        dominant = "balanced" if len(leaders) > 1 else leaders[0]
        return (
            f"Adaptive personality insights: recent dominant style is {dominant}. "
            f"Usage therapist={counts['therapist']}, coach={counts['coach']}, guide={counts['guide']}."
        )
