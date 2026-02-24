from datetime import datetime
from typing import Dict, List, Optional, Tuple


class GoalStrategyEngine:
    def ensure_shape(self, profile: dict):
        profile.setdefault("goal_strategy", {})
        gs = profile["goal_strategy"]
        gs.setdefault("miss_history", [])
        gs.setdefault("cause_counts", {})
        gs.setdefault("pending_miss_goal_id", "")
        gs.setdefault("last_recovery_prompt_date", "")

    def _match_goal(self, profile: dict, goal_ref: str) -> Optional[dict]:
        ref = (goal_ref or "").strip().lower()
        if not ref:
            return None
        for goal in profile.get("goals", []):
            gid = str(goal.get("id", "")).lower()
            title = str(goal.get("title", "")).lower()
            if gid == ref or gid.startswith(ref) or ref in title:
                return goal
        return None

    def _infer_cause(self, cause_text: str) -> str:
        t = (cause_text or "").lower()
        if any(k in t for k in ("tired", "sleepy", "energy", "exhausted", "fatigue")):
            return "energy"
        if any(k in t for k in ("busy", "late", "time", "schedule", "meeting")):
            return "time"
        if any(k in t for k in ("unclear", "confused", "not sure", "how")):
            return "clarity"
        if any(k in t for k in ("overwhelmed", "too much", "stress", "anxious")):
            return "overwhelm"
        return "other"

    def decompose_goal_text(self, goal_title: str) -> List[str]:
        title = (goal_title or "").strip()
        if not title:
            return []
        return [
            f"Define the exact output for: {title}",
            "Do one 10-minute starter action now.",
            "Do one 20-minute focused block.",
            "Close with a 2-minute review and mark progress.",
        ]

    def decompose_goal_by_ref(self, profile: dict, goal_ref: str) -> Tuple[bool, str]:
        goal = self._match_goal(profile, goal_ref)
        if not goal:
            return False, f"No goal found for '{goal_ref}'."
        steps = self.decompose_goal_text(str(goal.get("title", "")))
        if not steps:
            return False, "Could not decompose this goal."
        return True, "Micro-plan: " + " | ".join(f"{idx+1}. {s}" for idx, s in enumerate(steps))

    def mark_goal_missed(self, profile: dict, goal_ref: str, cause_text: str = "") -> Tuple[bool, str, str]:
        self.ensure_shape(profile)
        goal = self._match_goal(profile, goal_ref)
        if not goal:
            return False, f"No goal found for '{goal_ref}'.", ""

        now_iso = datetime.now().isoformat(timespec="seconds")
        cause = self._infer_cause(cause_text) if cause_text else ""
        self.ensure_shape(profile)
        gs = profile["goal_strategy"]
        gs["miss_history"].append(
            {
                "goal_id": goal.get("id", ""),
                "title": goal.get("title", ""),
                "scope": goal.get("scope", "general"),
                "missed_at": now_iso,
                "cause": cause,
                "cause_text": cause_text,
            }
        )
        gs["miss_history"] = gs["miss_history"][-80:]

        if cause:
            counts: Dict[str, int] = gs.get("cause_counts", {})
            counts[cause] = int(counts.get(cause, 0)) + 1
            gs["cause_counts"] = counts
            return True, f"Marked '{goal.get('title', '')}' as missed. Cause tracked as {cause}.", cause

        gs["pending_miss_goal_id"] = str(goal.get("id", ""))
        return True, (
            f"Marked '{goal.get('title', '')}' as missed. "
            "What was the main blocker: time, energy, clarity, or overwhelm?"
        ), ""

    def record_miss_cause(self, profile: dict, cause_text: str) -> str:
        self.ensure_shape(profile)
        gs = profile["goal_strategy"]
        pending_goal_id = str(gs.get("pending_miss_goal_id", ""))
        if not pending_goal_id:
            return "No pending missed goal. Use: mark goal missed <id or keyword>"

        cause = self._infer_cause(cause_text)
        counts: Dict[str, int] = gs.get("cause_counts", {})
        counts[cause] = int(counts.get(cause, 0)) + 1
        gs["cause_counts"] = counts

        for item in reversed(gs.get("miss_history", [])):
            if str(item.get("goal_id", "")) == pending_goal_id and not item.get("cause"):
                item["cause"] = cause
                item["cause_text"] = cause_text
                break

        gs["pending_miss_goal_id"] = ""
        return f"Saved miss root cause as {cause}."

    def root_cause_summary(self, profile: dict) -> str:
        self.ensure_shape(profile)
        counts: Dict[str, int] = profile["goal_strategy"].get("cause_counts", {})
        if not counts:
            return "Miss analysis: no root-cause data yet."
        ordered = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        top = ", ".join(f"{k}={v}" for k, v in ordered)
        top_cause = ordered[0][0]
        return f"Miss analysis: {top}. Primary blocker trend: {top_cause}."

    def context_summary(self, profile: dict) -> str:
        self.ensure_shape(profile)
        counts: Dict[str, int] = profile["goal_strategy"].get("cause_counts", {})
        if not counts:
            return "Goal strategy: no miss-cause trend yet."
        top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[0][0]
        return f"Goal strategy trend: common blocker is {top}."

    def recent_miss_count(self, profile: dict, days: int = 7) -> int:
        self.ensure_shape(profile)
        now = datetime.now()
        count = 0
        for item in profile["goal_strategy"].get("miss_history", []):
            try:
                dt = datetime.fromisoformat(str(item.get("missed_at", "")))
                if 0 <= (now - dt).days < max(1, int(days)):
                    count += 1
            except Exception:
                continue
        return count

    def blocker_coaching_line(self, profile: dict) -> str:
        self.ensure_shape(profile)
        counts: Dict[str, int] = profile["goal_strategy"].get("cause_counts", {})
        if not counts:
            return ""
        cause = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[0][0]
        if cause == "time":
            return "Primary blocker is time. Suggest time-boxed 10-minute starts."
        if cause == "energy":
            return "Primary blocker is energy. Suggest low-friction first step and earlier wind-down."
        if cause == "clarity":
            return "Primary blocker is clarity. Suggest breaking goals into smaller concrete outputs."
        if cause == "overwhelm":
            return "Primary blocker is overwhelm. Suggest reducing active goals and focusing one priority."
        return "Primary blocker trend detected. Keep steps small and specific."

    def should_trigger_recovery_protocol(self, profile: dict, days: int = 7, threshold: int = 2) -> bool:
        self.ensure_shape(profile)
        misses = self.recent_miss_count(profile, days=days)
        if misses < max(1, int(threshold)):
            return False

        today = datetime.now().date().isoformat()
        last = str(profile["goal_strategy"].get("last_recovery_prompt_date", ""))
        return last != today

    def mark_recovery_prompted_today(self, profile: dict):
        self.ensure_shape(profile)
        profile["goal_strategy"]["last_recovery_prompt_date"] = datetime.now().date().isoformat()

    def build_recovery_protocol_dialogue(self, profile: dict, active_goals: List[dict]) -> str:
        self.ensure_shape(profile)
        cause_line = self.blocker_coaching_line(profile) or "Identify the top blocker first."
        reduced = "sleep by your target bedtime"
        if active_goals:
            reduced = str(active_goals[0].get("title", reduced))
        return (
            "Recovery protocol: let's reset with three steps. "
            "1) Identify blocker now (time/energy/clarity/overwhelm). "
            f"2) Reduced goal for today: {reduced}. "
            "3) Start one 10-minute action immediately. "
            f"{cause_line}"
        )
