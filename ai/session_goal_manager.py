from datetime import datetime
from typing import List, Tuple
from uuid import uuid4


class SessionGoalManager:
    def ensure_shape(self, profile: dict):
        profile.setdefault("preferences", {})
        profile["preferences"].setdefault("goal_checkin_last_date", "")
        profile.setdefault("goals", [])
        cleaned = []
        for item in profile.get("goals", []):
            if not isinstance(item, dict):
                continue
            cleaned.append(
                {
                    "id": str(item.get("id", uuid4().hex[:6]))[:6],
                    "title": str(item.get("title", "")).strip(),
                    "scope": str(item.get("scope", "general")).strip() or "general",
                    "status": "done" if item.get("status") == "done" else "active",
                    "created_at": str(item.get("created_at", "")),
                    "completed_at": str(item.get("completed_at", "")),
                }
            )
        profile["goals"] = [g for g in cleaned if g["title"]]

    def add_goal(self, profile: dict, title: str, scope: str = "general") -> dict:
        self.ensure_shape(profile)
        goal = {
            "id": uuid4().hex[:6],
            "title": title.strip(),
            "scope": scope.strip() or "general",
            "status": "active",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "completed_at": "",
        }
        profile["goals"].append(goal)
        return goal

    def list_goals(self, profile: dict) -> List[dict]:
        self.ensure_shape(profile)
        return list(profile.get("goals", []))

    def complete_goal(self, profile: dict, goal_ref: str) -> Tuple[bool, str]:
        self.ensure_shape(profile)
        ref = (goal_ref or "").strip().lower()
        if not ref:
            return False, "Use: complete goal <id or keyword>"

        matches = []
        for goal in profile["goals"]:
            gid = goal["id"].lower()
            title = goal["title"].lower()
            if gid == ref or gid.startswith(ref) or ref in title:
                matches.append(goal)

        if not matches:
            return False, f"No goal found for '{goal_ref}'."

        goal = matches[0]
        if goal.get("status") == "done":
            return False, f"Goal '{goal['title']}' is already marked done."
        goal["status"] = "done"
        goal["completed_at"] = datetime.now().isoformat(timespec="seconds")
        return True, f"Great progress. Marked goal '{goal['title']}' as done."

    def clear_completed(self, profile: dict) -> int:
        self.ensure_shape(profile)
        before = len(profile["goals"])
        profile["goals"] = [g for g in profile["goals"] if g.get("status") != "done"]
        return before - len(profile["goals"])

    def context_summary(self, profile: dict) -> str:
        self.ensure_shape(profile)
        goals = profile.get("goals", [])
        active = [g for g in goals if g.get("status") == "active"]
        active_tonight = [g for g in active if g.get("scope", "").lower() == "tonight"]
        active_weekly = [g for g in active if g.get("scope", "").lower() == "weekly"]
        done = [g for g in goals if g.get("status") == "done"]
        active_titles = ", ".join(g["title"] for g in active[:2]) or "none"
        return (
            f"Active goals: {active_titles}. "
            f"Tonight goals: {len(active_tonight)}. Weekly goals: {len(active_weekly)}. "
            f"Completed goals count: {len(done)}."
        )

    def should_prompt_nightly_checkin(self, profile: dict, now: datetime = None) -> bool:
        self.ensure_shape(profile)
        now = now or datetime.now()
        if now.hour < 20:
            return False

        last_date = profile.get("preferences", {}).get("goal_checkin_last_date", "")
        if last_date == now.date().isoformat():
            return False

        active_tonight = [
            g
            for g in profile.get("goals", [])
            if g.get("status") == "active" and g.get("scope", "").lower() == "tonight"
        ]
        return bool(active_tonight)

    def build_nightly_checkin_prompt(self, profile: dict) -> str:
        self.ensure_shape(profile)
        active_tonight = [
            g
            for g in profile.get("goals", [])
            if g.get("status") == "active" and g.get("scope", "").lower() == "tonight"
        ]
        if not active_tonight:
            return ""

        top = active_tonight[0]
        return (
            f"Quick evening check-in: your tonight goal is '{top['title']}'. "
            "Do you want to mark progress or adjust the goal?"
        )

    def mark_nightly_checkin_prompted(self, profile: dict, now: datetime = None):
        self.ensure_shape(profile)
        now = now or datetime.now()
        profile["preferences"]["goal_checkin_last_date"] = now.date().isoformat()
