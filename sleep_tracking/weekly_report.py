from __future__ import annotations

import datetime
import json
import os

from sleep_tracking.sleep_score import SleepScoreCalculator


class WeeklyReportGenerator:
    def __init__(self):
        self.log_file = os.path.join(os.path.dirname(__file__), "sessions_log.json")
        self.score_calculator = SleepScoreCalculator()

    def _read_log(self) -> list[dict]:
        if not os.path.exists(self.log_file):
            return []
        try:
            with open(self.log_file, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return []
        return payload if isinstance(payload, list) else []

    @staticmethod
    def _parse_dt(value: str) -> datetime.datetime | None:
        try:
            return datetime.datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def _session_date(self, session: dict) -> datetime.date | None:
        end_dt = self._parse_dt(str(session.get("sleep_end", "")))
        if end_dt:
            return end_dt.date()
        start_dt = self._parse_dt(str(session.get("sleep_start", "")))
        if start_dt:
            return start_dt.date()
        return None

    def _session_score(self, session: dict) -> int:
        if session.get("sleep_score") is not None:
            try:
                return int(session.get("sleep_score"))
            except (TypeError, ValueError):
                pass

        total_hours = float(session.get("total_hours", 0.0) or 0.0)
        quality_rating = session.get("quality_rating")
        quality_value = int(quality_rating) if quality_rating is not None else 3
        start_dt = self._parse_dt(str(session.get("sleep_start", "")))
        end_dt = self._parse_dt(str(session.get("sleep_end", "")))
        sleep_hour = start_dt.hour if start_dt else 0
        wake_hour = end_dt.hour if end_dt else 7
        return self.score_calculator.calculate_score(
            total_hours=total_hours,
            quality_rating=quality_value,
            sleep_hour=sleep_hour,
            wake_hour=wake_hour,
        )

    @staticmethod
    def _calculate_streak(dates: list[datetime.date]) -> int:
        if not dates:
            return 0
        unique_desc = sorted(set(dates), reverse=True)
        streak = 1
        expected = unique_desc[0] - datetime.timedelta(days=1)
        for current in unique_desc[1:]:
            if current == expected:
                streak += 1
                expected = expected - datetime.timedelta(days=1)
                continue
            break
        return streak

    def generate_report(self, user_id: str) -> dict:
        sessions = [
            item for item in self._read_log()
            if isinstance(item, dict)
            and str(item.get("user_id")) == str(user_id)
            and str(item.get("status", "")) == "completed"
        ]

        today = datetime.date.today()
        current_start = today - datetime.timedelta(days=6)
        prev_start = today - datetime.timedelta(days=13)
        prev_end = today - datetime.timedelta(days=7)

        current_week: list[dict] = []
        previous_week: list[dict] = []
        all_dates: list[datetime.date] = []

        for session in sessions:
            session_date = self._session_date(session)
            if session_date is None:
                continue
            all_dates.append(session_date)
            if current_start <= session_date <= today:
                current_week.append(session)
            elif prev_start <= session_date <= prev_end:
                previous_week.append(session)

        if not current_week:
            return {
                "avg_sleep_hours": 0.0,
                "avg_score": 0.0,
                "best_night": None,
                "worst_night": None,
                "total_nights_tracked": 0,
                "streak_days": self._calculate_streak(all_dates),
                "improvement": 0.0,
            }

        enriched: list[dict] = []
        for session in current_week:
            entry = dict(session)
            entry["score"] = self._session_score(session)
            entry["session_date"] = self._session_date(session).isoformat() if self._session_date(session) else ""
            enriched.append(entry)

        avg_sleep_hours = round(
            sum(float(item.get("total_hours", 0.0) or 0.0) for item in enriched) / len(enriched),
            2,
        )
        avg_score = round(sum(int(item.get("score", 0)) for item in enriched) / len(enriched), 2)

        best = max(enriched, key=lambda item: int(item.get("score", 0)))
        worst = min(enriched, key=lambda item: int(item.get("score", 0)))

        prev_scores = [self._session_score(item) for item in previous_week]
        prev_avg = (sum(prev_scores) / len(prev_scores)) if prev_scores else avg_score
        improvement = round(avg_score - prev_avg, 2)

        return {
            "avg_sleep_hours": avg_sleep_hours,
            "avg_score": avg_score,
            "best_night": {
                "date": best.get("session_date", ""),
                "score": int(best.get("score", 0)),
            },
            "worst_night": {
                "date": worst.get("session_date", ""),
                "score": int(worst.get("score", 0)),
            },
            "total_nights_tracked": len(enriched),
            "streak_days": self._calculate_streak(all_dates),
            "improvement": improvement,
        }

    def get_report_summary_text(self, report: dict) -> str:
        total_nights = int(report.get("total_nights_tracked", 0) or 0)
        if total_nights <= 0:
            return "No sleep sessions were tracked this week yet. Start tonight and Dana will build your report."

        avg_hours = float(report.get("avg_sleep_hours", 0.0) or 0.0)
        avg_score = float(report.get("avg_score", 0.0) or 0.0)
        best_night = report.get("best_night", {}) if isinstance(report.get("best_night", {}), dict) else {}
        best_date_text = str(best_night.get("date", "")).strip()
        best_day = "your best night"
        if best_date_text:
            try:
                best_day = datetime.date.fromisoformat(best_date_text).strftime("%A")
            except ValueError:
                best_day = "your best night"

        return (
            f"This week you slept an average of {avg_hours:.1f} hours with a score of {avg_score:.0f}/100. "
            f"Your best night was {best_day}. MashaAllah, keep it up!"
        )
