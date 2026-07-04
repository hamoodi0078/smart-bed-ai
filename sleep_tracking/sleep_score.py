from __future__ import annotations


class SleepScoreCalculator:
    def calculate_score(
        self,
        total_hours: float,
        quality_rating: int,
        sleep_hour: int,
        wake_hour: int,
    ) -> int:
        _ = wake_hour
        hours = float(total_hours or 0.0)
        rating = max(0, min(5, int(quality_rating or 0)))

        if 7 <= hours <= 9:
            hours_score = 40
        elif (6 <= hours < 7) or (9 < hours <= 10):
            hours_score = 30
        elif (5 <= hours < 6) or (hours > 10):
            hours_score = 20
        else:
            hours_score = 10

        quality_score = rating * 6

        sleep_hour_normalized = int(sleep_hour) % 24
        if sleep_hour_normalized >= 22:
            consistency_score = 30
        elif sleep_hour_normalized == 0:
            consistency_score = 20
        elif sleep_hour_normalized == 1:
            consistency_score = 10
        else:
            consistency_score = 0

        total = hours_score + quality_score + consistency_score
        return max(0, min(100, int(total)))

    def get_score_label(self, score: int) -> str:
        value = int(score)
        if 90 <= value <= 100:
            return "Excellent 🌟"
        if 70 <= value <= 89:
            return "Good 👍"
        if 50 <= value <= 69:
            return "Fair ⚠️"
        return "Poor 😴"

    def get_score_advice(self, score: int, total_hours: float) -> str:
        value = int(score)
        hours = float(total_hours or 0.0)

        if value >= 90:
            return "Excellent recovery. Keep this same routine and bedtime consistency."
        if value >= 70:
            if hours < 7:
                return (
                    "Good quality overall. Try adding 30-60 minutes of sleep for better recovery."
                )
            return "Strong sleep result. Keep your bedtime and wake time steady."
        if value >= 50:
            if hours < 6:
                return "Your sleep duration is low. Prioritize a longer sleep window tonight."
            return "Sleep is fair. Improve consistency by sleeping earlier."
        if hours < 5:
            return "Very short sleep detected. Aim for at least 7 hours and reduce late-night stimulation."
        return "Sleep quality needs support. Use a longer wind-down and keep a consistent bedtime."
