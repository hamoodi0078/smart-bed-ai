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

try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing as _HoltWinters
    from statsmodels.tsa.seasonal import seasonal_decompose as _seasonal_decompose
    from statsmodels.tsa.stattools import acf as _acf
    from statsmodels.tsa.stattools import adfuller as _adfuller
    _STATSMODELS_AVAILABLE = True
except ImportError:
    _STATSMODELS_AVAILABLE = False

try:
    import litellm as _litellm
    _LITELLM_AVAILABLE = True
except ImportError:
    _litellm = None  # type: ignore[assignment]
    _LITELLM_AVAILABLE = False

try:
    from langchain_core.prompts import ChatPromptTemplate as _ChatPromptTemplate
    from langchain_core.prompts import PromptTemplate as _PromptTemplate
    from langchain_core.output_parsers import StrOutputParser as _StrOutputParser
    _LANGCHAIN_CORE_AVAILABLE = True
    _lc_str_parser = _StrOutputParser()
except ImportError:
    _LANGCHAIN_CORE_AVAILABLE = False
    _lc_str_parser = None  # type: ignore[assignment]


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

        # Augment with ADF stationarity test on the bedtime series when statsmodels
        # is available — gives statistical confidence rather than just a mean diff.
        stationarity: dict[str, Any] = {}
        if _STATSMODELS_AVAILABLE and len(normalized) >= 8:
            try:
                adf_stat, p_value, *_ = _adfuller(np.array(normalized, dtype=float), autolag="AIC")
                stationarity = {
                    "adf_statistic": round(float(adf_stat), 4),
                    "p_value": round(float(p_value), 4),
                    "statistically_stable": bool(p_value <= 0.05),
                }
                # Override drift_detected when ADF says the series IS stationary.
                if stationarity["statistically_stable"] and drift_minutes <= 30:
                    drift_detected = False
            except Exception:
                pass

        return {
            "drift_detected": drift_detected,
            "drift_minutes": round(drift_minutes, 1),
            "message": message,
            "nights_analyzed": len(bed_times),
            "intervention_level": 3 if drift_minutes > 60 else (2 if drift_minutes > 45 else (1 if drift_detected else 0)),
            "stationarity_test": stationarity,
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

    def calculate_sleep_efficiency(
        self,
        total_sleep_minutes: float | None = None,
        time_in_bed_minutes: float | None = None,
        sleep_start: str = "",
        sleep_end: str = "",
        awakenings_minutes: float = 0.0,
    ) -> dict[str, Any]:
        """Compute sleep efficiency (WASO-adjusted) as a percentage.

        Sleep efficiency = total sleep time / time in bed × 100.
        Clinical normal range is 85-100%.  Below 80% is a clinical marker for
        insomnia and warrants intervention.

        Parameters accept either (total_sleep, time_in_bed) or ISO strings for
        sleep_start / sleep_end + optional minutes of awakenings.
        """
        tst = total_sleep_minutes
        tib = time_in_bed_minutes

        # Derive TIB from start/end strings if explicit values not provided
        if (tst is None or tib is None) and sleep_start and sleep_end:
            try:
                fmt = "%H:%M"
                start_dt = datetime.strptime(sleep_start[:5], fmt)
                end_dt = datetime.strptime(sleep_end[:5], fmt)
                if end_dt <= start_dt:
                    end_dt += timedelta(days=1)
                tib = (end_dt - start_dt).total_seconds() / 60.0
                tst = max(0.0, tib - float(awakenings_minutes or 0))
            except Exception:
                pass

        if tst is None or tib is None or tib <= 0:
            return {"available": False, "reason": "Insufficient data to calculate sleep efficiency"}

        efficiency = min(100.0, (float(tst) / float(tib)) * 100.0)
        rating: str
        if efficiency >= 85:
            rating = "normal"
        elif efficiency >= 75:
            rating = "below_average"
        else:
            rating = "poor"

        return {
            "available": True,
            "sleep_efficiency_pct": round(efficiency, 1),
            "total_sleep_minutes": round(float(tst), 1),
            "time_in_bed_minutes": round(float(tib), 1),
            "rating": rating,
            "waso_minutes": round(float(awakenings_minutes or 0), 1),
            "recommendation": (
                "Sleep efficiency is normal." if rating == "normal"
                else "Consider restricting time in bed to improve efficiency."
                if rating == "below_average"
                else "Poor sleep efficiency — consider CBT-I or sleep restriction therapy."
            ),
        }

    def calculate_social_jet_lag(
        self, profile: dict, weeks: int = 4
    ) -> dict[str, Any]:
        """Compute social jet lag: the difference between weekday and weekend mid-sleep times.

        Social jet lag ≥ 2 hours is associated with higher metabolic risk, mood
        impairment, and daytime sleepiness.  The mid-sleep time is the midpoint
        between sleep onset and wake time, which is a chronobiologically meaningful
        marker of the circadian phase.

        Returns absolute social jet lag in hours plus a severity rating.
        """
        sleep = profile.get("sleep", {}) if isinstance(profile, dict) else {}
        bed_hist = sleep.get("bedtime_history", []) if isinstance(sleep.get("bedtime_history"), list) else []
        wake_hist = sleep.get("wake_history", []) if isinstance(sleep.get("wake_history"), list) else []

        # Limit to the last N weeks (7 * weeks nights)
        max_nights = 7 * max(1, int(weeks))
        bed_times = self._parse_timestamps(bed_hist[-max_nights:])
        wake_times = self._parse_timestamps(wake_hist[-max_nights:])
        pairs = min(len(bed_times), len(wake_times))

        if pairs < 4:
            return {"available": False, "reason": "Need at least 4 bed/wake pairs to calculate social jet lag."}

        weekday_mids: list[float] = []
        weekend_mids: list[float] = []

        for i in range(1, pairs + 1):
            bed = bed_times[-i]
            wake = wake_times[-i]
            if wake <= bed:
                continue
            # Mid-sleep in minutes from midnight
            duration_min = (wake - bed).total_seconds() / 60.0
            bed_min = _minutes_of_day(bed)
            mid_min = (bed_min + duration_min / 2.0) % (24 * 60)
            if bed.weekday() < 5:
                weekday_mids.append(mid_min)
            else:
                weekend_mids.append(mid_min)

        if not weekday_mids or not weekend_mids:
            return {"available": False, "reason": "Need both weekday and weekend data to calculate social jet lag."}

        wd_mid = _circular_mean_minutes([int(m) for m in weekday_mids])
        we_mid = _circular_mean_minutes([int(m) for m in weekend_mids])

        # Smallest circular difference (minutes)
        diff = float(we_mid - wd_mid)
        if diff > 12 * 60:
            diff -= 24 * 60
        elif diff < -12 * 60:
            diff += 24 * 60

        sjl_hours = abs(diff) / 60.0

        if sjl_hours < 1.0:
            severity = "low"
            message = "Minimal social jet lag. Your circadian rhythm is well-aligned."
        elif sjl_hours < 2.0:
            severity = "moderate"
            message = f"{sjl_hours:.1f}h social jet lag. Consider shifting your weekend sleep 15–30 min earlier each night."
        else:
            severity = "high"
            message = (
                f"{sjl_hours:.1f}h social jet lag — higher metabolic and mood risk. "
                "Gradually align weekend sleep to within 1 hour of your weekday schedule."
            )

        return {
            "available": True,
            "social_jet_lag_hours": round(sjl_hours, 2),
            "weekday_mid_sleep": _minutes_to_hhmm(wd_mid),
            "weekend_mid_sleep": _minutes_to_hhmm(we_mid),
            "direction": "weekend_later" if diff > 0 else "weekend_earlier",
            "severity": severity,
            "message": message,
            "weekday_nights": len(weekday_mids),
            "weekend_nights": len(weekend_mids),
        }

    def forecast_sleep_duration(
        self, profile: dict, nights: int = 3
    ) -> dict[str, Any]:
        """Forecast the next *nights* nights of sleep duration using Holt-Winters
        exponential smoothing.

        Returns forecasted hours per night plus a confidence interval derived
        from the in-sample residual standard deviation. Falls back to a simple
        rolling mean when statsmodels is unavailable or data is too short.
        """
        sleep = profile.get("sleep", {}) if isinstance(profile, dict) else {}
        bed_hist = sleep.get("bedtime_history", []) or []
        wake_hist = sleep.get("wake_history", []) or []
        bed_times = self._parse_timestamps(bed_hist[-60:])
        wake_times = self._parse_timestamps(wake_hist[-60:])
        durations = self._calculate_durations(bed_times, wake_times)

        nights = max(1, min(int(nights), 14))

        if len(durations) < 4:
            return {"available": False, "reason": "Need at least 4 nights of data."}

        series = pd.Series(durations, dtype=float)

        if not _STATSMODELS_AVAILABLE or len(durations) < 8:
            # Simple fallback: EWM with span=7
            ewm_mean = float(series.ewm(span=7, adjust=False).mean().iloc[-1])
            ewm_std = float(series.ewm(span=7, adjust=False).std().iloc[-1]) or 0.3
            forecasts = [round(ewm_mean, 2)] * nights
            return {
                "available": True,
                "method": "ewm_fallback",
                "forecasts_hours": forecasts,
                "confidence_interval_95": [
                    round(ewm_mean - 1.96 * ewm_std, 2),
                    round(ewm_mean + 1.96 * ewm_std, 2),
                ],
                "nights_ahead": nights,
                "based_on_nights": len(durations),
            }

        try:
            model = _HoltWinters(
                series,
                trend="add",
                seasonal=None,
                initialization_method="estimated",
            )
            fit = model.fit(optimized=True, disp=False)
            raw_fc = fit.forecast(nights)
            residual_std = float(fit.resid.std()) or 0.3

            forecasts = [round(max(1.0, min(16.0, float(v))), 2) for v in raw_fc]
            ci_half = round(1.96 * residual_std, 2)
            return {
                "available": True,
                "method": "holt_winters",
                "forecasts_hours": forecasts,
                "confidence_interval_95": [
                    round(forecasts[0] - ci_half, 2),
                    round(forecasts[0] + ci_half, 2),
                ],
                "residual_std": round(residual_std, 3),
                "nights_ahead": nights,
                "based_on_nights": len(durations),
            }
        except Exception as exc:
            return {"available": False, "reason": str(exc)}

    def decompose_sleep_pattern(self, profile: dict) -> dict[str, Any]:
        """Seasonal decomposition of nightly sleep duration (period = 7 days).

        Separates the signal into trend, weekly seasonal cycle, and residual
        noise. Requires at least 14 paired nights (two full weekly cycles).

        Returns trend direction ('improving' | 'declining' | 'stable'),
        the strength of the weekly seasonal effect, and the peak/trough days.
        """
        if not _STATSMODELS_AVAILABLE:
            return {"available": False, "reason": "statsmodels not installed"}

        sleep = profile.get("sleep", {}) if isinstance(profile, dict) else {}
        bed_hist = sleep.get("bedtime_history", []) or []
        wake_hist = sleep.get("wake_history", []) or []
        bed_times = self._parse_timestamps(bed_hist[-60:])
        wake_times = self._parse_timestamps(wake_hist[-60:])
        durations = self._calculate_durations(bed_times, wake_times)

        if len(durations) < 14:
            return {"available": False, "reason": "Need at least 14 nights for weekly decomposition."}

        try:
            series = pd.Series(
                durations,
                index=pd.date_range(end=pd.Timestamp.today().normalize(), periods=len(durations), freq="D"),
                dtype=float,
            )
            result = _seasonal_decompose(series, model="additive", period=7, extrapolate_trend="freq")

            trend_vals = result.trend.dropna()
            trend_diff = float(trend_vals.iloc[-1]) - float(trend_vals.iloc[0])
            if trend_diff > 0.25:
                trend_direction = "improving"
            elif trend_diff < -0.25:
                trend_direction = "declining"
            else:
                trend_direction = "stable"

            seasonal = result.seasonal
            seasonal_strength = round(float(seasonal.std()), 3)
            peak_day = int(seasonal.groupby(seasonal.index.dayofweek).mean().idxmax())
            trough_day = int(seasonal.groupby(seasonal.index.dayofweek).mean().idxmin())
            day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

            residual_std = round(float(result.resid.dropna().std()), 3)

            return {
                "available": True,
                "trend_direction": trend_direction,
                "trend_change_hours": round(trend_diff, 2),
                "seasonal_strength_hours": seasonal_strength,
                "peak_sleep_day": day_names[peak_day],
                "trough_sleep_day": day_names[trough_day],
                "residual_noise_std": residual_std,
                "nights_analyzed": len(durations),
            }
        except Exception as exc:
            return {"available": False, "reason": str(exc)}

    def test_stationarity(self, profile: dict) -> dict[str, Any]:
        """Augmented Dickey-Fuller test on sleep duration series.

        A stationary series (p ≤ 0.05) means sleep duration has no systematic
        drift — good news. A non-stationary series (p > 0.05) indicates a
        unit root: sleep duration is drifting, which may need intervention.

        Also returns the lag-1 autocorrelation so callers can see whether
        last night's sleep predicts tonight's.
        """
        if not _STATSMODELS_AVAILABLE:
            return {"available": False, "reason": "statsmodels not installed"}

        sleep = profile.get("sleep", {}) if isinstance(profile, dict) else {}
        bed_hist = sleep.get("bedtime_history", []) or []
        wake_hist = sleep.get("wake_history", []) or []
        bed_times = self._parse_timestamps(bed_hist[-60:])
        wake_times = self._parse_timestamps(wake_hist[-60:])
        durations = self._calculate_durations(bed_times, wake_times)

        if len(durations) < 8:
            return {"available": False, "reason": "Need at least 8 nights for stationarity test."}

        try:
            series = np.array(durations, dtype=float)
            adf_stat, p_value, used_lags, nobs, critical_values, _ = _adfuller(series, autolag="AIC")

            is_stationary = bool(p_value <= 0.05)
            interpretation = (
                "Sleep duration is stationary — no systematic drift detected."
                if is_stationary
                else "Sleep duration shows drift — a consistent pattern change is underway."
            )

            lag1_acf = float(_acf(series, nlags=1, fft=True)[1]) if len(series) >= 4 else 0.0

            return {
                "available": True,
                "is_stationary": is_stationary,
                "adf_statistic": round(float(adf_stat), 4),
                "p_value": round(float(p_value), 4),
                "used_lags": int(used_lags),
                "observations": int(nobs),
                "critical_values": {k: round(v, 3) for k, v in critical_values.items()},
                "lag1_autocorrelation": round(lag1_acf, 3),
                "interpretation": interpretation,
            }
        except Exception as exc:
            return {"available": False, "reason": str(exc)}

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


class LLMSleepInsights:
    """Generate plain-language sleep coaching insights via litellm.

    Wraps SleepAnalyzer outputs and routes to any litellm-supported model
    (Anthropic, OpenAI, Gemini, Ollama, …) to produce actionable advice.
    Degrades gracefully when litellm is absent or no key is set.

    Parameters
    ----------
    model:
        LiteLLM model string, e.g. ``"anthropic/claude-haiku-4-5-20251001"``,
        ``"gpt-4o-mini"``, ``"gemini/gemini-1.5-flash"``.
    api_key:
        Optional explicit API key — overrides the environment variable.
    timeout_seconds:
        Per-call hard timeout.
    num_retries:
        Automatic retry count forwarded to litellm on transient errors.
    temperature:
        Sampling temperature; lower = more deterministic coaching copy.
    """

    DEFAULT_MODEL = "anthropic/claude-haiku-4-5-20251001"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: str = "",
        timeout_seconds: int = 15,
        num_retries: int = 2,
        temperature: float = 0.4,
    ) -> None:
        self._model = str(model or self.DEFAULT_MODEL).strip()
        self._api_key = str(api_key or "").strip() or None
        self._timeout_seconds = int(timeout_seconds)
        self._num_retries = max(0, int(num_retries))
        self._temperature = max(0.0, min(2.0, float(temperature)))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_insight(self, analysis: dict[str, Any]) -> str:
        """Return actionable coaching text from analyze_patterns() output.

        Returns an empty string when litellm is unavailable or the call fails.
        """
        if not _LITELLM_AVAILABLE or _litellm is None:
            return ""
        return self._call(self._build_pattern_prompt(analysis), max_tokens=200)

    def generate_forecast_insight(self, forecast: dict[str, Any]) -> str:
        """Return a short coaching note from forecast_sleep_duration() output."""
        if not _LITELLM_AVAILABLE or _litellm is None or not forecast.get("available"):
            return ""
        hours_list = forecast.get("forecasts_hours", [])
        if not hours_list:
            return ""
        avg_h = round(sum(hours_list) / len(hours_list), 1)
        ci = forecast.get("confidence_interval_95", [])
        ci_str = f"{ci[0]}–{ci[1]}h" if len(ci) == 2 else "N/A"
        method = forecast.get("method", "model")
        nights = forecast.get("nights_ahead", 1)
        prompt = (
            f"A {method} sleep forecast predicts {avg_h} hours/night over the next "
            f"{nights} night(s) (95% CI: {ci_str}). "
            "Give one brief, practical coaching tip. "
            "Max 2 sentences — do not echo the numbers."
        )
        return self._call(prompt, max_tokens=100)

    def generate_drift_insight(self, drift: dict[str, Any]) -> str:
        """Return a coaching note from detect_bedtime_drift() output."""
        if not _LITELLM_AVAILABLE or _litellm is None:
            return ""
        detected = drift.get("drift_detected", False)
        minutes = drift.get("drift_minutes", 0.0)
        level = drift.get("intervention_level", 0)
        if not detected or level == 0:
            return ""
        prompt = (
            f"A user's bedtime has drifted {abs(minutes):.0f} minutes later "
            f"(intervention level {level}/3). "
            "Give one specific, actionable tip to correct this drift. "
            "Max 2 sentences. Sound warm, not clinical."
        )
        return self._call(prompt, max_tokens=100)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    # langchain-core PromptTemplate for the sleep pattern coaching prompt.
    # Curly-brace variables are filled at call time via .format().
    _PATTERN_TEMPLATE: Any = (
        _PromptTemplate.from_template(
            "Sleep summary ({nights} nights):\n"
            "- Avg sleep: {avg_h}h | Trend: {trend}\n"
            "- Avg bedtime: {avg_bed} | Avg wake: {avg_wake}\n"
            "- Best bedtime (when user slept longest): {optimal}\n"
            "- Consistency — bedtime: {bed_c}/100, wake: {wake_c}/100\n"
            "- Short nights (<6h): {short} | Late nights (past 1am): {late}\n\n"
            "Give 1-3 specific, actionable sleep coaching tips based on this data. "
            "Be concise and warm. Do not repeat numbers. Max 3 sentences."
        )
        if _LANGCHAIN_CORE_AVAILABLE
        else None
    )

    def _call(self, prompt: str, max_tokens: int = 200) -> str:
        kwargs: dict[str, Any] = dict(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=self._temperature,
            timeout=self._timeout_seconds,
            num_retries=self._num_retries,
            drop_params=True,
        )
        if self._api_key:
            kwargs["api_key"] = self._api_key
        try:
            response = _litellm.completion(**kwargs)  # type: ignore[union-attr]
            raw = str(
                (response.choices[0].message.content or "") if response.choices else ""
            ).strip()
            # Run through StrOutputParser for standard langchain-core output handling.
            return _lc_str_parser.parse(raw) if _LANGCHAIN_CORE_AVAILABLE and _lc_str_parser else raw
        except Exception:
            return ""

    @staticmethod
    def _build_pattern_prompt(analysis: dict[str, Any]) -> str:
        nights = analysis.get("total_nights_analyzed", 0)
        avg_h = analysis.get("avg_sleep_hours", 0)
        bed_c = analysis.get("bedtime_consistency_score", 0)
        wake_c = analysis.get("wake_consistency_score", 0)
        trend = analysis.get("trend", "unknown")
        optimal = analysis.get("optimal_bedtime", "N/A")
        short = analysis.get("short_sleep_count", 0)
        late = analysis.get("late_night_count", 0)
        avg_bed = analysis.get("avg_bedtime", "N/A")
        avg_wake = analysis.get("avg_wake_time", "N/A")

        if _LANGCHAIN_CORE_AVAILABLE and LLMSleepInsights._PATTERN_TEMPLATE is not None:
            return LLMSleepInsights._PATTERN_TEMPLATE.format(
                nights=nights, avg_h=avg_h, trend=trend,
                avg_bed=avg_bed, avg_wake=avg_wake, optimal=optimal,
                bed_c=bed_c, wake_c=wake_c, short=short, late=late,
            )

        return (
            f"Sleep summary ({nights} nights):\n"
            f"- Avg sleep: {avg_h}h | Trend: {trend}\n"
            f"- Avg bedtime: {avg_bed} | Avg wake: {avg_wake}\n"
            f"- Best bedtime (when user slept longest): {optimal}\n"
            f"- Consistency — bedtime: {bed_c}/100, wake: {wake_c}/100\n"
            f"- Short nights (<6h): {short} | Late nights (past 1am): {late}\n\n"
            "Give 1-3 specific, actionable sleep coaching tips based on this data. "
            "Be concise and warm. Do not repeat numbers. Max 3 sentences."
        )
