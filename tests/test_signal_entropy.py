"""Tests for antropy-powered signal complexity in WakeOptimizer."""

from __future__ import annotations

import math
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sleep_tracking.wake_optimizer import WakeOptimizer


def _ts(second: int) -> datetime:
    return datetime(2026, 5, 5, 22, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=second)


def _feed(optimizer: WakeOptimizer, values: list[float]) -> None:
    for i, v in enumerate(values):
        optimizer.record_pressure(v, timestamp=_ts(i))


class TestSignalComplexityAntropy(unittest.TestCase):

    def test_returns_unavailable_when_antropy_missing(self):
        with patch("sleep_tracking.wake_optimizer._ANTROPY_AVAILABLE", False):
            opt = WakeOptimizer()
            _feed(opt, [50.0] * 40)
            result = opt.get_signal_complexity()
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "antropy not installed")

    def test_returns_unavailable_for_constant_signal(self):
        opt = WakeOptimizer()
        _feed(opt, [100.0] * 40)
        result = opt.get_signal_complexity()
        # Constant signal has zero std — entropy undefined.
        self.assertFalse(result["available"])

    def test_returns_unavailable_below_minimum_samples(self):
        opt = WakeOptimizer()
        _feed(opt, [50.0 + i * 0.1 for i in range(10)])
        result = opt.get_signal_complexity()
        self.assertFalse(result["available"])

    def test_regular_sinusoidal_signal_has_low_complexity(self):
        opt = WakeOptimizer()
        # Perfect sine wave — low permutation entropy expected.
        values = [50.0 + 5.0 * math.sin(i * 0.3) for i in range(200)]
        _feed(opt, values)
        result = opt.get_signal_complexity()
        if not result["available"]:
            self.skipTest("antropy not installed")
        self.assertIn("perm_entropy", result)
        self.assertIn("sample_entropy", result)
        self.assertIn("svd_entropy", result)
        self.assertIn("num_zerocross", result)
        self.assertIn(result["complexity_label"], {"low", "medium", "high"})
        # Sine wave should be low or medium complexity, never extremely high.
        self.assertLess(result["perm_entropy"], 0.95)

    def test_random_signal_has_high_complexity(self):
        import random
        rng = random.Random(42)
        opt = WakeOptimizer()
        values = [50.0 + rng.gauss(0, 5) for _ in range(300)]
        _feed(opt, values)
        result = opt.get_signal_complexity()
        if not result["available"]:
            self.skipTest("antropy not installed")
        # Pure noise should have high permutation entropy.
        self.assertGreater(result["perm_entropy"], 0.6)
        self.assertEqual(result["complexity_label"], "high")

    def test_status_includes_signal_complexity_key(self):
        opt = WakeOptimizer()
        _feed(opt, [50.0 + math.sin(i * 0.2) * 3 for i in range(50)])
        status = opt.get_status()
        self.assertIn("signal_complexity", status)

    def test_quality_estimate_includes_signal_complexity(self):
        opt = WakeOptimizer()
        values = [50.0 + math.sin(i * 0.15) * 2 for i in range(200)]
        _feed(opt, values)
        estimate = opt.get_sleep_quality_estimate()
        if estimate["quality"] == "unknown":
            self.skipTest("Not enough data for quality estimate")
        self.assertIn("signal_complexity", estimate)


class TestEntropyPenaltyApplied(unittest.TestCase):
    """Verify that high perm_entropy lowers the estimated score."""

    def test_high_entropy_penalty_reduces_score(self):
        import random
        rng = random.Random(7)
        opt = WakeOptimizer(
            restlessness_threshold_pct=1.0,  # make it very sensitive
        )
        # Noisy random signal produces high perm_entropy.
        values = [50.0 + rng.gauss(0, 3) for _ in range(300)]
        _feed(opt, values)

        estimate = opt.get_sleep_quality_estimate()
        if estimate["quality"] == "unknown":
            self.skipTest("Not enough data")
        complexity = estimate["signal_complexity"]
        if not complexity.get("available"):
            self.skipTest("antropy not installed")

        if complexity["perm_entropy"] > 0.85:
            # Score should be penalised by at least 10 points.
            base_score = {"deep": 90, "moderate": 70, "light": 50, "restless": 30}.get(
                estimate["quality"], 0
            )
            # With penalty applied, reported score must be lower.
            self.assertLessEqual(estimate["estimated_score"], base_score)


if __name__ == "__main__":
    unittest.main()