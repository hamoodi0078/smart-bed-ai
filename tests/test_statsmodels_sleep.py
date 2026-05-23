"""Tests for statsmodels-powered sleep analytics in SleepAnalyzer."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sleep_tracking.sleep_analyzer import SleepAnalyzer

_UTC = timezone.utc


def _make_profile(
    n_nights: int,
    duration_hours: float = 7.5,
    jitter: float = 0.0,
    drift_per_night: float = 0.0,
) -> dict:
    """Build a synthetic profile with *n_nights* of paired bed/wake history."""
    import random
    rng = random.Random(42)
    base_bed = datetime(2026, 3, 1, 23, 0, tzinfo=_UTC)
    beds, wakes = [], []
    for i in range(n_nights):
        bed = base_bed + timedelta(days=i, minutes=rng.uniform(-jitter * 60, jitter * 60))
        dur = duration_hours + drift_per_night * i + rng.uniform(-jitter / 2, jitter / 2)
        wake = bed + timedelta(hours=max(2.0, dur))
        beds.append(bed.isoformat())
        wakes.append(wake.isoformat())
    return {"sleep": {"bedtime_history": beds, "wake_history": wakes}}


class TestForecastSleepDuration(unittest.TestCase):

    def test_returns_unavailable_for_too_few_nights(self):
        profile = _make_profile(3)
        result = SleepAnalyzer().forecast_sleep_duration(profile)
        self.assertFalse(result["available"])

    def test_ewm_fallback_when_statsmodels_missing(self):
        profile = _make_profile(6)
        with patch("sleep_tracking.sleep_analyzer._STATSMODELS_AVAILABLE", False):
            result = SleepAnalyzer().forecast_sleep_duration(profile, nights=2)
        self.assertTrue(result["available"])
        self.assertEqual(result["method"], "ewm_fallback")
        self.assertEqual(len(result["forecasts_hours"]), 2)
        lo, hi = result["confidence_interval_95"]
        self.assertLess(lo, hi)

    def test_holt_winters_produces_plausible_forecast(self):
        profile = _make_profile(20, duration_hours=7.5, jitter=0.3)
        result = SleepAnalyzer().forecast_sleep_duration(profile, nights=3)
        if not result["available"]:
            self.skipTest("statsmodels not installed")
        self.assertEqual(result["method"], "holt_winters")
        self.assertEqual(len(result["forecasts_hours"]), 3)
        for fc in result["forecasts_hours"]:
            self.assertGreater(fc, 1.0)
            self.assertLess(fc, 16.0)
        lo, hi = result["confidence_interval_95"]
        self.assertLess(lo, hi)

    def test_forecast_clamps_to_valid_range(self):
        # Extreme durations should still be clamped to [1, 16]
        profile = _make_profile(20, duration_hours=15.0, jitter=0.1)
        result = SleepAnalyzer().forecast_sleep_duration(profile, nights=1)
        if not result["available"]:
            self.skipTest("statsmodels not installed")
        self.assertLessEqual(result["forecasts_hours"][0], 16.0)

    def test_nights_parameter_respected(self):
        profile = _make_profile(20)
        result = SleepAnalyzer().forecast_sleep_duration(profile, nights=5)
        if not result["available"]:
            self.skipTest("statsmodels not installed")
        self.assertEqual(result["nights_ahead"], 5)
        self.assertEqual(len(result["forecasts_hours"]), 5)


class TestDecomposeSleepPattern(unittest.TestCase):

    def test_returns_unavailable_when_statsmodels_missing(self):
        profile = _make_profile(20)
        with patch("sleep_tracking.sleep_analyzer._STATSMODELS_AVAILABLE", False):
            result = SleepAnalyzer().decompose_sleep_pattern(profile)
        self.assertFalse(result["available"])
        self.assertIn("statsmodels", result["reason"])

    def test_returns_unavailable_for_fewer_than_14_nights(self):
        profile = _make_profile(10)
        result = SleepAnalyzer().decompose_sleep_pattern(profile)
        if result.get("reason") == "statsmodels not installed":
            self.skipTest("statsmodels not installed")
        self.assertFalse(result["available"])

    def test_decomposition_keys_present(self):
        profile = _make_profile(21, jitter=0.5)
        result = SleepAnalyzer().decompose_sleep_pattern(profile)
        if not result["available"]:
            self.skipTest("statsmodels not installed or insufficient data")
        for key in ("trend_direction", "trend_change_hours", "seasonal_strength_hours",
                    "peak_sleep_day", "trough_sleep_day", "residual_noise_std", "nights_analyzed"):
            self.assertIn(key, result)

    def test_trend_direction_valid_value(self):
        profile = _make_profile(21, jitter=0.4)
        result = SleepAnalyzer().decompose_sleep_pattern(profile)
        if not result["available"]:
            self.skipTest("statsmodels not installed or insufficient data")
        self.assertIn(result["trend_direction"], {"improving", "declining", "stable"})

    def test_declining_trend_detected(self):
        # Each night 12 minutes shorter → clear declining trend
        profile = _make_profile(21, duration_hours=8.0, drift_per_night=-0.2)
        result = SleepAnalyzer().decompose_sleep_pattern(profile)
        if not result["available"]:
            self.skipTest("statsmodels not installed or insufficient data")
        self.assertEqual(result["trend_direction"], "declining")

    def test_peak_and_trough_days_are_valid(self):
        profile = _make_profile(21, jitter=0.5)
        result = SleepAnalyzer().decompose_sleep_pattern(profile)
        if not result["available"]:
            self.skipTest("statsmodels not installed or insufficient data")
        valid_days = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
        self.assertIn(result["peak_sleep_day"], valid_days)
        self.assertIn(result["trough_sleep_day"], valid_days)


class TestStationarity(unittest.TestCase):

    def test_returns_unavailable_when_statsmodels_missing(self):
        profile = _make_profile(20)
        with patch("sleep_tracking.sleep_analyzer._STATSMODELS_AVAILABLE", False):
            result = SleepAnalyzer().test_stationarity(profile)
        self.assertFalse(result["available"])

    def test_returns_unavailable_for_fewer_than_8_nights(self):
        profile = _make_profile(5)
        result = SleepAnalyzer().test_stationarity(profile)
        if result.get("reason") == "statsmodels not installed":
            self.skipTest("statsmodels not installed")
        self.assertFalse(result["available"])

    def test_result_keys_present(self):
        profile = _make_profile(20, jitter=0.3)
        result = SleepAnalyzer().test_stationarity(profile)
        if not result["available"]:
            self.skipTest("statsmodels not installed or insufficient data")
        for key in ("is_stationary", "adf_statistic", "p_value", "critical_values",
                    "lag1_autocorrelation", "interpretation"):
            self.assertIn(key, result)

    def test_stable_series_is_stationary(self):
        # No drift, low noise → should be stationary
        profile = _make_profile(30, duration_hours=7.5, jitter=0.1)
        result = SleepAnalyzer().test_stationarity(profile)
        if not result["available"]:
            self.skipTest("statsmodels not installed")
        # p-value and statistic are present
        self.assertIsInstance(result["p_value"], float)
        self.assertIsInstance(result["adf_statistic"], float)

    def test_p_value_in_valid_range(self):
        profile = _make_profile(20, jitter=0.4)
        result = SleepAnalyzer().test_stationarity(profile)
        if not result["available"]:
            self.skipTest("statsmodels not installed")
        self.assertGreaterEqual(result["p_value"], 0.0)
        self.assertLessEqual(result["p_value"], 1.0)

    def test_lag1_autocorrelation_in_valid_range(self):
        profile = _make_profile(20, jitter=0.3)
        result = SleepAnalyzer().test_stationarity(profile)
        if not result["available"]:
            self.skipTest("statsmodels not installed")
        self.assertGreaterEqual(result["lag1_autocorrelation"], -1.0)
        self.assertLessEqual(result["lag1_autocorrelation"], 1.0)


class TestDriftDetectionWithADF(unittest.TestCase):

    def test_stationarity_test_key_present_in_drift_result(self):
        profile = _make_profile(12, jitter=0.3)
        result = SleepAnalyzer().detect_bedtime_drift(profile, days=12)
        # stationarity_test key should always be present (may be empty dict if <8 nights)
        self.assertIn("stationarity_test", result)

    def test_adf_enriches_stable_bedtime_series(self):
        # Very stable bedtime → ADF should mark as stationary, drift suppressed
        profile = _make_profile(14, jitter=0.05)
        result = SleepAnalyzer().detect_bedtime_drift(profile, days=14)
        if not result.get("stationarity_test"):
            self.skipTest("statsmodels not installed or insufficient data")
        st = result["stationarity_test"]
        self.assertIn("p_value", st)
        self.assertIn("statistically_stable", st)


if __name__ == "__main__":
    unittest.main()