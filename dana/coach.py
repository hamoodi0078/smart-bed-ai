from __future__ import annotations


class DanaCoach:
    def get_bedtime_message(self, hour: int) -> str:
        if hour < 22:
            return "Early to bed — champion move! 💪"
        if hour < 24:
            return "Good timing! Consistent sleep builds champions."
        return "You're running late. Recovery starts NOW."

    def get_streak_message(self, streak_days: int) -> str:
        if streak_days == 1:
            return "Day 1 done! The journey begins."
        if streak_days == 7:
            return "7-night streak! You're building a habit!"
        if streak_days == 30:
            return "30 NIGHTS! You are a sleep champion! 🏆"
        return f"{streak_days}-night streak! Keep pushing!"

    def get_sleep_score_message(self, score: int) -> str:
        if 90 <= score <= 100:
            return "PERFECT score! Elite recovery!"
        if 70 <= score <= 89:
            return "Strong performance! Push for 90+"
        if 50 <= score <= 69:
            return "Room to improve. Let's optimize tonight."
        return "Tough night. Adjust your routine and come back stronger."

    def get_weekly_report_message(self, avg_score: float, best_night: int) -> str:
        if avg_score >= 90:
            tone = "Elite consistency this week!"
        elif avg_score >= 75:
            tone = "Strong momentum. Keep your routine locked in."
        elif avg_score >= 60:
            tone = "Solid effort with room to level up."
        else:
            tone = "This was a tough week, but your comeback starts tonight."
        return (
            f"{tone} Weekly average sleep score: {avg_score:.1f}. Best night score: {best_night}."
        )
