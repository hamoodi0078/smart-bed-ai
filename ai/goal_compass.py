from datetime import datetime


class GoalCompass:
    def ensure_shape(self, profile: dict):
        profile.setdefault("goal_compass", {})
        gc = profile["goal_compass"]
        gc.setdefault("monthly_objective", "")
        gc.setdefault("updated_at", "")

    def set_monthly_objective(self, profile: dict, objective: str) -> str:
        self.ensure_shape(profile)
        text = (objective or "").strip()
        profile["goal_compass"]["monthly_objective"] = text
        profile["goal_compass"]["updated_at"] = datetime.now().isoformat(timespec="seconds")
        return "Monthly objective saved." if text else "Monthly objective cleared."

    def get_monthly_objective(self, profile: dict) -> str:
        self.ensure_shape(profile)
        return str(profile["goal_compass"].get("monthly_objective", "")).strip()

    def summary_line(self, profile: dict, active_goals: list) -> str:
        self.ensure_shape(profile)
        objective = self.get_monthly_objective(profile)
        if not objective:
            return "Goal compass: no monthly objective set yet."
        top_goals = ", ".join(g.get("title", "") for g in active_goals[:2]) or "none"
        return f"Goal compass: monthly objective='{objective}'. Active goals now: {top_goals}."
