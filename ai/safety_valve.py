from datetime import datetime


class SafetyValve:
    """Escalates conversational role to therapist after sustained distress."""

    def __init__(self, distress_turn_threshold: int = 3):
        self.distress_turn_threshold = max(2, int(distress_turn_threshold))

    def ensure_shape(self, profile: dict):
        profile.setdefault("safety_valve", {})
        state = profile["safety_valve"]
        state.setdefault("distress_streak", 0)
        state.setdefault("last_escalated_at", "")

    def apply(self, profile: dict, base_personality: str, emotion_state: str, safety_level: str = "none") -> tuple[str, str]:
        self.ensure_shape(profile)
        state = profile["safety_valve"]

        personality = str(base_personality or "therapist").strip().lower()
        emotion = str(emotion_state or "neutral").strip().lower()
        safety = str(safety_level or "none").strip().lower()

        if safety in ("high", "moderate"):
            state["distress_streak"] = max(self.distress_turn_threshold, int(state.get("distress_streak", 0)))
        elif emotion == "distressed":
            state["distress_streak"] = int(state.get("distress_streak", 0)) + 1
        else:
            state["distress_streak"] = max(0, int(state.get("distress_streak", 0)) - 1)

        if int(state.get("distress_streak", 0)) >= self.distress_turn_threshold and personality != "therapist":
            state["last_escalated_at"] = datetime.now().isoformat(timespec="seconds")
            return "therapist", "safety_valve_distress_escalation"

        return personality, "base"
