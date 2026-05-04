"""Sleep pattern analysis engine for Smart Bed AI.

Analyzes bedtime/wake history to detect patterns, predict optimal bedtime,
calculate consistency scores, and identify weekday vs weekend differences.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _minutes_of_day(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def _minutes_to_hhmm(minutes: int) -> str:
    minutes = minutes % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _circular_mean_minutes(values: list[int]) -> int:
    """Circular mean for time-of-day values (handles midnight wrap)."""
    if not values:
        return 0
    arr = np.asarray(values, dtype=float)
    radians = arr / (24 * 60) * 2 * np.pi
    mean_rad = np.arctan2(np.sin(radians).mean(), np.cos(radians).mean())
    if mean_rad < 0:
        mean_rad += 2 * np.pi
    return int(round(float(mean_rad) / (2 * np.pi) * (24 * 60))) % (24 * 60)


class SleepAnalyzer:
    """Analyzes sleep history to detect patterns and predict optimal schedules."""

    def analyze_patterns(self, profile: dict) -> dict[str, Any]:
        """Full pattern analysis from profile sleep data."""
        sleep = profile.get("sleep", {}) if isinstance(profile, dict) else {}
        bed_hist = sleep.get("bedtime_history", []) if isinstance(sleep.get("bedtime_history"), list) else []
        wake_hist = sleep.get("wake_history", []) if isinstance(sleep.get("wake_history"), list) else []

        bed_times = self._parse_timestamps(bed_hist[-30:])
        wake_times = self._parse_timestamps(wake_hist[-30:])

        durations = self._calculate_durations(bed_times, wake_times)
        bed_minutes = [_minutes_of_day(dt) for dt in bed_times]
        wake_minutes = [_minutes_of_day(dt) for dt in wake_times]

        weekday_beds, weekend_beds = self._split_weekday_weekend(bed_times)
        weekday_wakes, weekend_wakes = self._split_weekday_weekend(wake_times)

        s = pd.Series(durations, dtype=float)
        return {
            "total_nights_analyzed": len(durations),
            "avg_sleep_hours": round(float(s.mean()), 2) if not s.empty else 0.0,
            "median_sleep_hours": round(float(s.median()), 2) if not s.empty else 0.0,
            "stddev_sleep_hours": round(float(s.std()), 2) if len(s) > 1 else 0.0,
            "avg_bedtime": _minutes_to_hhmm(_circular_mean_minutes(bed_minutes)) if bed_minutes else "N/A",
            "avg_wake_time": _minutes_to_hhmm(_circular_mean_minutes(wake_minutes)) if wake_minutes else "N/A",
            "bedtime_consistency_score": self._consistency_score(bed_minutes),
            "wake_consistency_score": self._consistency_score(wake_minutes),
            "weekday_avg_bedtime": _minutes_to_hhmm(_circular_mean_minutes(
                [_minutes_of_day(dt) for dt in weekday_beds]
            )) if weekday_beds else "N/A",
            "weekend_avg_bedtime": _minutes_to_hhmm(_circular_mean_minutes(
                [_minutes_of_day(dt) for dt in weekend_beds]
            )) if weekend_beds else "N/A",
            "weekday_avg_wake": _minutes_to_hhmm(_circular_mean_minutes(
                [_minutes_of_day(dt) for dt in weekday_wakes]
            )) if weekday_wakes else "N/A",
            "weekend_avg_wake": _minutes_to_hhmm(_circular_mean_minutes(
                [_minutes_of_day(dt) for dt in weekend_wakes]
            )) if weekend_wakes else "N/A",
            "late_night_count": sum(1 for m in bed_minutes if 60 <= m <= 180),
            "short_sleep_count": sum(1 for d in durations if d < 6.0),
            "optimal_bedtime": self._predict_optimal_bedtime(bed_minutes, durations),
            "trend": self._calculate_trend(durations),
        }

    def predict_bedtime(self, profile: dict, target_wake_time: str = "") -> dict[str, Any]:
        """Predict optimal bedtime based on history and optional target wake time."""
        sleep = profile.get("sleep", {}) if isinstance(profile, dict) else {}
        bed_hist = sleep.get("bedtime_history", []) if isinstance(sleep.get("bedtime_history"), list) else []
        wake_hist = sleep.get("wake_history", []) if isinstance(sleep.get("wake_history"), list) else []

        bed_times = self._parse_timestamps(bed_hist[-14:])
        wake_times = self._parse_timestamps(wake_hist[-14:])
        durations = self._calculate_durations(bed_times, wake_times)

        avg_duration = float(pd.Series(durations, dtype=float).mean()) if durations else 7.5
        target_hours = float(profile.get("preferences", {}).get("sleep_target_hours", 8.0) or 8.0)
        recommended_hours = max(target_hours, min(avg_duration + 0.5, 9.0))

        if target_wake_time:
            try:
                parts = target_wake_time.split(":")
                wake_minutes = int(parts[0]) * 60 + int(parts[1])
            except Exception:
                wake_minutes = _circular_mean_minutes([_minutes_of_day(dt) for dt in wake_times]) if wake_times else 420
        else:
            wake_minutes = _circular_mean_minutes([_minutes_of_day(dt) for dt in wake_times]) if wake_times else 420

        bedtime_minutes = int(wake_minutes - recommended_hours * 60)
        if bedtime_minutes < 0:
            bedtime_minutes += 24 * 60

        window_start = (bedtime_minutes - 15) % (24 * 60)
        window_end = (bedtime_minutes + 15) % (24 * 60)

        return {
            "recommended_bedtime": _minutes_to_hhmm(bedtime_minutes),
            "bedtime_window": f"{_minutes_to_hhmm(window_start)}-{_minutes_to_hhmm(window_end)}",
            "recommended_hours": round(recommended_hours, 1),
            "target_wake": _minutes_to_hhmm(wake_minutes),
            "based_on_nights": len(durations),
        }

    def detect_bedtime_drift(self, profile: dict, days: int = 7) -> dict[str, Any]:
        """Detect if user's bedtime is drifting later over recent nights."""
        sleep = profile.get("sleep", {}) if isinstance(profile, dict) else {}
        bed_hist = sleep.get("bedtime_history", []) if isinstance(sleep.get("bedtime_history"), list) else []
        bed_times = self._parse_timestamps(bed_hist[-days:])

        if len(bed_times) < 3:
            return {"drift_detected": False, "message": "Not enough data to detect drift."}

        bed_minutes = [_minutes_of_day(dt) for dt in bed_times]
        # Normalize around midnight for comparison
        normalized = []
        for m in bed_minutes:
            if m < 360:  # before 6 AM → treat as past midnight
                normalized.append(m + 24 * 60)
            else:
                normalized.append(m)

        norm_s = pd.Series(normalized, dtype=float)
        mid = len(norm_s) // 2
        avg_first = float(norm_s.iloc[:mid].mean()) if mid > 0 else 0.0
        avg_second = float(norm_s.iloc[mid:].mean()) if mid < len(norm_s) else 0.0
        drift_minutes = avg_second - avg_first

        drift_detected = drift_minutes > 20

        message = ""
        if drift_minutes > 45:
            message = f"Significant bedtime drift: sleeping {int(drift_minutes)} minutes later than your earlier pattern."
        elif drift_minutes > 20:
            message = f"Mild bedtime drift: about {int(drift_minutes)} minutes later than before."
        else:
            message = "Your bedtime is consistent. Keep it up!"

        return {
            "drift_detected": drift_detected,
            "drift_minutes": round(drift_minutes, 1),
            "message": message,
            "nights_analyzed": len(bed_times),
            "intervention_level": 3 if drift_minutes > 60 else (2 if drift_minutes > 45 else (1 if drift_detected else 0)),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_timestamps(iso_list: list) -> list[datetime]:
        results = []
        for raw in iso_list:
            try:
                dt = datetime.fromisoformat(str(raw))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                results.append(dt)
            except Exception:
                continue
        return results

    @staticmethod
    def _calculate_durations(bed_times: list[datetime], wake_times: list[datetime]) -> list[float]:
        pairs = min(len(bed_times), len(wake_times))
        durations = []
        for i in range(1, pairs + 1):
            bed = bed_times[-i]
            wake = wake_times[-i]
            if wake <= bed:
                continue
            hours = (wake - bed).total_seconds() / 3600.0
            if 2.0 <= hours <= 16.0:
                durations.append(hours)
        return durations

    @staticmethod
    def _split_weekday_weekend(timestamps: list[datetime]) -> tuple[list[datetime], list[datetime]]:
        weekday = [dt for dt in timestamps if dt.weekday() < 5]
        weekend = [dt for dt in timestamps if dt.weekday() >= 5]
        return weekday, weekend

    @staticmethod
    def _consistency_score(minutes_list: list[int]) -> int:
        """0-100 score where 100 = perfectly consistent bedtime/wake time."""
        if len(minutes_list) < 2:
            return 100
        arr = np.asarray(minutes_list, dtype=float)
        radians = arr / (24 * 60) * 2 * np.pi
        r = float(np.sqrt(np.sin(radians).mean() ** 2 + np.cos(radians).mean() ** 2))
        return max(0, min(100, int(r * 100)))

    def _predict_optimal_bedtime(self, bed_minutes: list[int], durations: list[float]) -> str:
        """Predict the best bedtime based on when the user sleeps best."""
        if not bed_minutes or not durations:
            return "22:30"

        best_nights = sorted(
            zip(bed_minutes, durations),
            key=lambda pair: pair[1],
            reverse=True,
        )[:5]

        if best_nights:
            best_bedtime_minutes = _circular_mean_minutes([m for m, _ in best_nights])
            return _minutes_to_hhmm(best_bedtime_minutes)
        return "22:30"

    @staticmethod
    def _calculate_trend(durations: list[float]) -> str:
        """Detect if sleep duration is improving, declining, or stable."""
        if len(durations) < 4:
            return "insufficient_data"
        s = pd.Series(durations, dtype=float)
        mid = len(s) // 2
        first_half = float(s.iloc[:mid].mean())
        second_half = float(s.iloc[mid:].mean())
        diff = second_half - first_half
        if diff > 0.3:
            return "improving"
        if diff < -0.3:
            return "declining"
        return "stable"

    def detect_anomalous_nights(self, profile: dict, contamination: float = 0.1) -> dict[str, Any]:
        """Use IsolationForest to flag nights with unusual sleep duration or timing.

        Features: [sleep_hours, bedtime_minutes_normalized]
        Requires at least 7 paired bed/wake entries for a meaningful model.
        """
        sleep = profile.get("sleep", {}) if isinstance(profile, dict) else {}
        bed_hist = sleep.get("bedtime_history", []) if isinstance(sleep.get("bedtime_history"), list) else []
        wake_hist = sleep.get("wake_history", []) if isinstance(sleep.get("wake_history"), list) else []

        bed_times = self._parse_timestamps(bed_hist[-60:])
        wake_times = self._parse_timestamps(wake_hist[-60:])
        durations = self._calculate_durations(bed_times, wake_times)
        bed_minutes = [_minutes_of_day(dt) for dt in bed_times[-len(durations):]]

        if len(durations) < 7:
            return {"anomalous_nights": [], "message": "Not enough data (need ≥7 nights)."}

        X = np.column_stack([
            np.array(durations, dtype=float),
            np.array(bed_minutes, dtype=float) / (24 * 60),  # normalize to [0, 1]
        ])
        X_scaled = StandardScaler().fit_transform(X)

        clf = IsolationForest(
            contamination=max(0.05, min(0.5, float(contamination))),
            random_state=42,
            n_estimators=100,
        )
        labels = clf.fit_predict(X_scaled)  # -1 = anomaly, 1 = normal
        scores = clf.decision_function(X_scaled)  # lower = more anomalous

        anomalous = [
            {
                "night_index": int(i),
                "sleep_hours": round(float(durations[i]), 2),
                "bedtime": _minutes_to_hhmm(int(bed_minutes[i])),
                "anomaly_score": round(float(scores[i]), 4),
            }
            for i in range(len(labels))
            if labels[i] == -1
        ]

        return {
            "nights_analyzed": len(durations),
            "anomalous_nights": anomalous,
            "anomalous_count": len(anomalous),
        }
