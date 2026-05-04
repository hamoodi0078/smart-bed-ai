from datetime import datetime
from typing import List, Dict


class ProactiveAutomationEngine:
    def ensure_shape(self, profile: dict):
        profile.setdefault("proactive", {})
        proactive = profile["proactive"]
        proactive.setdefault("sent_keys", [])
        proactive.setdefault("history", [])
        proactive.setdefault("verbosity", "normal")

    def _is_in_quiet_window(self, quiet_window: str, now: datetime) -> bool:
        text = (quiet_window or "").strip()
        if not text or "-" not in text:
            return False
        try:
            left, right = [p.strip() for p in text.split("-", 1)]
            sh, sm = [int(x) for x in left.split(":", 1)]
            eh, em = [int(x) for x in right.split(":", 1)]
            start_m = sh * 60 + sm
            end_m = eh * 60 + em
            now_m = now.hour * 60 + now.minute
            if start_m == end_m:
                return False
            if start_m < end_m:
                return start_m <= now_m < end_m
            return now_m >= start_m or now_m < end_m
        except Exception:
            return False

    def _window_bucket(self, now: datetime) -> str:
        if 5 <= now.hour <= 11:
            return "morning"
        if 18 <= now.hour <= 23:
            return "evening"
        return "general"

    def _already_sent(self, profile: dict, key: str, now: datetime) -> bool:
        self.ensure_shape(profile)
        today = now.date().isoformat()
        window = self._window_bucket(now)
        for item in profile["proactive"].get("sent_keys", [])[-80:]:
            if item.get("key") == key and item.get("date") == today and item.get("window") == window:
                return True
        return False

    def _mark_sent(self, profile: dict, action: Dict, now: datetime):
        self.ensure_shape(profile)
        today = now.date().isoformat()
        window = self._window_bucket(now)
        key = str(action.get("key", "")).strip()
        sent = profile["proactive"].get("sent_keys", [])
        sent.append({"key": key, "date": today, "window": window})
        profile["proactive"]["sent_keys"] = sent[-120:]

        history = profile["proactive"].get("history", [])
        history.append(
            {
                "key": key,
                "line": str(action.get("line", "")).strip(),
                "executed_at": now.isoformat(timespec="seconds"),
                "window": window,
            }
        )
        profile["proactive"]["history"] = history[-120:]

    def mark_executed(self, profile: dict, action: Dict, now: datetime | None = None):
        now = now or datetime.now()
        self._mark_sent(profile, action, now)

    def evaluate(self, profile: dict, now: datetime, session_state: dict) -> List[dict]:
        self.ensure_shape(profile)
        suggestions: List[dict] = []

        quiet_window = profile.get("preferences", {}).get("quiet_window", "")
        if self._is_in_quiet_window(quiet_window, now):
            return suggestions

        interrupts = int(session_state.get("interrupt_count_today", 0) or 0)
        active_goals_count = int(session_state.get("active_goals_count", 0) or 0)
        sleep = profile.get("sleep", {})
        invisible_routine = session_state.get("invisible_routine", {})

        if isinstance(invisible_routine, dict) and bool(invisible_routine.get("prep_window_active", False)):
            key = "invisible_guide_prep"
            if not self._already_sent(profile, key, now):
                suggestions.append(
                    {
                        "key": key,
                        "type": "action_bundle",
                        "intent": "set_scene",
                        "slots": {
                            "scene_key": "calm_recovery",
                            "brightness": 0.18,
                            "color": "warmwhite",
                            "animation": "breathing",
                        },
                        "line": str(
                            invisible_routine.get(
                                "offer_line",
                                "I quietly prepared your guide environment. Want to begin now?",
                            )
                        ).strip(),
                    }
                )

        if interrupts >= 4:
            profile["proactive"]["verbosity"] = "minimal"
            key = "overload_simplification_prompt"
            if not self._already_sent(profile, key, now):
                suggestions.append(
                    {
                        "key": key,
                        "type": "prompt",
                        "line": "I will keep tonight simple: one tiny priority, calm lighting, and fewer prompts unless you ask.",
                    }
                )

        if 17 <= now.hour <= 23:
            key = "bedtime_drift_intervention"
            if (not self._already_sent(profile, key, now)) and str(session_state.get("bedtime_drift_alert") or "").startswith("Predictive alert:"):
                suggestions.append(
                    {
                        "key": key,
                        "type": "announce",
                        "line": str(session_state.get("bedtime_drift_alert", "")).strip(),
                    }
                )

        if 0 <= now.hour <= 5:
            night_wakes = int(sleep.get("night_wake_count", 0) or 0)
            if night_wakes > 0:
                key = "night_wake_rescue"
                if not self._already_sent(profile, key, now):
                    suggestions.append(
                        {
                            "key": key,
                            "type": "action_bundle",
                            "intent": "night_wake_recovery",
                            "line": "I can run night wake rescue now: ultra-dim scene, slower breathing rhythm, and short calming guidance.",
                        }
                    )

        if 5 <= now.hour <= 11 and bool(profile.get("preferences", {}).get("adaptive_wake_enabled", True)):
            key = "adaptive_morning_ramp"
            if not self._already_sent(profile, key, now):
                suggestions.append(
                    {
                        "key": key,
                        "type": "prompt",
                        "intent": "adaptive_wake_ramp",
                        "line": "Morning ramp is ready: gentle light progression and a soft wake sequence.",
                    }
                )

        if active_goals_count >= 3:
            key = "goal_overload_simplification"
            if not self._already_sent(profile, key, now):
                suggestions.append(
                    {
                        "key": key,
                        "type": "prompt",
                        "line": "You have a high goal load tonight. I recommend reducing to one must-do and one optional task.",
                    }
                )

        return suggestions

    def daily_summary(self, profile: dict, now: datetime | None = None) -> str:
        self.ensure_shape(profile)
        now = now or datetime.now()
        today = now.date().isoformat()
        items = [x for x in profile.get("proactive", {}).get("history", []) if str(x.get("executed_at", "")).startswith(today)]
        if not items:
            return "Today I did not auto-manage anything yet."
        lines = [str(x.get("line", "")).strip() for x in items if str(x.get("line", "")).strip()]
        lines = lines[:4]
        return "Auto-managed today: " + " | ".join(lines)
