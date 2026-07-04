"""Property-based tests using Hypothesis for Smart Bed AI invariants.

Each test verifies a *mathematical invariant* — a property that must hold for
any input Hypothesis generates, not just the examples we happen to think of.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from hypothesis import given, settings, assume
from hypothesis import strategies as st

# First-run import costs can exceed hypothesis' default 200ms deadline and
# make these tests flaky in full-suite runs; the invariants themselves are
# order-of-milliseconds, so wall-clock deadlines add no value here.
settings.register_profile("no_deadline", deadline=None)
settings.load_profile("no_deadline")

# ---------------------------------------------------------------------------
# Strategies shared across suites
# ---------------------------------------------------------------------------

_HH_MM = st.builds(
    lambda h, m: f"{h:02d}:{m:02d}",
    h=st.integers(min_value=0, max_value=23),
    m=st.integers(min_value=0, max_value=59),
)

_QUIET_WINDOW = st.builds(
    lambda start, end: f"{start}-{end}",
    start=_HH_MM,
    end=_HH_MM,
)

_ISO_DATETIME = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31, 23, 59, 59),
    timezones=st.just(timezone.utc),
).map(lambda dt: dt.isoformat())

_SLEEP_HOURS = st.floats(min_value=2.0, max_value=14.0, allow_nan=False, allow_infinity=False)

_JSON_PRIMITIVE = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-10_000, max_value=10_000),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=40),
)

_JSON_LEAF = st.recursive(
    _JSON_PRIMITIVE,
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(max_size=10), children, max_size=5),
    ),
    max_leaves=20,
)


# ===========================================================================
# 1. automations.registry — quiet-hours logic
# ===========================================================================


class TestQuietHoursInvariants(unittest.TestCase):
    """is_in_quiet_hours() must always return a bool and never raise."""

    @given(
        hour=st.integers(min_value=0, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
        quiet_window=_QUIET_WINDOW,
        quiet_mode_active=st.booleans(),
    )
    def test_always_returns_bool(self, hour, minute, quiet_window, quiet_mode_active):
        from automations.registry import is_in_quiet_hours

        now = datetime(2025, 6, 15, hour, minute, 0, tzinfo=timezone.utc)
        result = is_in_quiet_hours(
            now_local=now,
            quiet_window=quiet_window,
            quiet_mode_active=quiet_mode_active,
        )
        self.assertIsInstance(result, bool)

    @given(
        hour=st.integers(min_value=0, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
        quiet_window=st.text(max_size=30),  # arbitrary garbage strings
    )
    def test_garbage_window_string_never_raises(self, hour, minute, quiet_window):
        from automations.registry import is_in_quiet_hours

        now = datetime(2025, 6, 15, hour, minute, 0, tzinfo=timezone.utc)
        result = is_in_quiet_hours(now_local=now, quiet_window=quiet_window)
        self.assertIsInstance(result, bool)

    @given(
        hour=st.integers(min_value=0, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
        quiet_window=_QUIET_WINDOW,
    )
    def test_quiet_mode_active_always_true(self, hour, minute, quiet_window):
        from automations.registry import is_in_quiet_hours

        now = datetime(2025, 6, 15, hour, minute, 0, tzinfo=timezone.utc)
        self.assertTrue(
            is_in_quiet_hours(now_local=now, quiet_window=quiet_window, quiet_mode_active=True)
        )


# ===========================================================================
# 2. health.weekly_health_report — output shape invariants
# ===========================================================================


class TestWeeklyReportInvariants(unittest.TestCase):
    """WeeklyHealthReport must produce consistently shaped, bounded output."""

    def _make_profile(self, bed_times, wake_times, target_hours=8.0):
        return {
            "preferences": {"sleep_target_hours": target_hours},
            "sleep": {
                "bedtime_history": bed_times,
                "wake_history": wake_times,
            },
            "stress": {"history": []},
            "hydration": {"history": []},
            "islamic": {"prayer_stats": {}, "tahajjud_history": []},
            "proactive": {"history": []},
            "daily_life": {"overthinking_entries": []},
        }

    @given(
        bed_times=st.lists(_ISO_DATETIME, min_size=0, max_size=7),
        wake_times=st.lists(_ISO_DATETIME, min_size=0, max_size=7),
        target=st.floats(min_value=4.0, max_value=12.0, allow_nan=False),
    )
    def test_compile_sleep_bounds(self, bed_times, wake_times, target):
        from health.weekly_health_report import WeeklyHealthReport

        reporter = WeeklyHealthReport()
        profile = self._make_profile(bed_times, wake_times, target)
        result = reporter._compile_sleep(profile)

        self.assertGreaterEqual(result["avg_hours"], 0)
        self.assertGreaterEqual(result["total_debt_hours"], 0)
        self.assertGreaterEqual(result["nights_tracked"], 0)
        self.assertGreaterEqual(result["short_nights"], 0)
        self.assertLessEqual(result["short_nights"], result["nights_tracked"])
        self.assertGreaterEqual(result["consistency_score"], 0)
        self.assertLessEqual(result["consistency_score"], 100)

    @given(
        avg_hours=st.floats(min_value=0, max_value=12, allow_nan=False),
        consistency=st.integers(min_value=0, max_value=100),
        debt=st.floats(min_value=0, max_value=20, allow_nan=False),
        short_nights=st.integers(min_value=0, max_value=7),
        avg_stress=st.floats(min_value=0, max_value=100, allow_nan=False),
        overthinking=st.integers(min_value=0, max_value=20),
        goal_rate=st.floats(min_value=0, max_value=100, allow_nan=False),
    )
    def test_recommendations_length_always_1_to_5(
        self,
        avg_hours,
        consistency,
        debt,
        short_nights,
        avg_stress,
        overthinking,
        goal_rate,
    ):
        from health.weekly_health_report import WeeklyHealthReport

        reporter = WeeklyHealthReport()
        fake_report = {
            "sleep": {
                "avg_hours": avg_hours,
                "consistency_score": consistency,
                "total_debt_hours": debt,
                "short_nights": short_nights,
            },
            "wellness": {
                "avg_stress_score": avg_stress,
                "overthinking_entries": overthinking,
            },
            "hydration": {"goal_rate_pct": goal_rate},
        }
        recs = reporter._build_recommendations(fake_report)
        self.assertGreaterEqual(len(recs), 1)
        self.assertLessEqual(len(recs), 5)
        for r in recs:
            self.assertIsInstance(r, str)
            self.assertGreater(len(r), 0)

    @given(
        report_day=st.integers(min_value=0, max_value=6),
        report_hour=st.integers(min_value=0, max_value=23),
    )
    def test_init_clamps_day_and_hour(self, report_day, report_hour):
        from health.weekly_health_report import WeeklyHealthReport

        reporter = WeeklyHealthReport(report_day=report_day, report_hour=report_hour)
        self.assertGreaterEqual(reporter._report_day, 0)
        self.assertLessEqual(reporter._report_day, 6)
        self.assertGreaterEqual(reporter._report_hour, 0)
        self.assertLessEqual(reporter._report_hour, 23)

    @given(report_day=st.integers(min_value=-100, max_value=200))
    def test_init_clamps_out_of_range_day(self, report_day):
        from health.weekly_health_report import WeeklyHealthReport

        reporter = WeeklyHealthReport(report_day=report_day)
        self.assertGreaterEqual(reporter._report_day, 0)
        self.assertLessEqual(reporter._report_day, 6)


# ===========================================================================
# 3. core.analytics_engine — engagement score always [0, 100]
# ===========================================================================


class TestAnalyticsEngineInvariants(unittest.TestCase):
    """calculate_engagement_score() must always return a score in [0, 100]."""

    def setUp(self):
        from core.analytics_engine import AnalyticsEngine

        self._tmp = tempfile.TemporaryDirectory()
        self.engine = AnalyticsEngine(data_dir=Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    @given(
        event_types=st.lists(
            st.sampled_from(
                [
                    "sleep_session_end",
                    "voice_command",
                    "scene_activated",
                    "automation_accepted",
                    "wind_down_completed",
                    "prayer_reminder_acknowledged",
                    "breathing_exercise_completed",
                    "mood_logged",
                    "app_opened",
                    "bed_entry",
                    "automation_declined",
                    "alarm_triggered",
                ]
            ),
            min_size=0,
            max_size=50,
        ),
        days=st.integers(min_value=1, max_value=90),
    )
    @settings(max_examples=50)
    def test_engagement_score_always_in_range(self, event_types, days):
        user_id = "hyp_test_user"
        for et in event_types:
            self.engine.track(et, user_id=user_id)
        result = self.engine.calculate_engagement_score(user_id, days=days)
        score = result["score"]
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)
        self.assertIsInstance(result["label"], str)

    @given(days=st.integers(min_value=1, max_value=365))
    def test_empty_engine_engagement_score_is_zero(self, days):
        result = self.engine.calculate_engagement_score("nobody", days=days)
        self.assertEqual(result["score"], 0)

    @given(
        event_type=st.text(max_size=50),
        days=st.integers(min_value=1, max_value=30),
    )
    def test_count_events_never_negative(self, event_type, days):
        count = self.engine.count_events(event_type, days=days)
        self.assertGreaterEqual(count, 0)


# ===========================================================================
# 4. Storage.io — atomic write round-trips arbitrary JSON
# ===========================================================================


class TestStorageIoRoundTrip(unittest.TestCase):
    """atomic_write_json + locked_read_json must survive any JSON-serializable dict."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "sub" / "data.json"

    def tearDown(self):
        self._tmp.cleanup()

    @given(
        payload=st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=_JSON_LEAF,
            max_size=10,
        )
    )
    def test_round_trip(self, payload):
        from Storage.io import atomic_write_json, locked_read_json

        assume(json.dumps(payload))  # skip if not JSON-serializable
        atomic_write_json(self.path, payload)
        loaded = locked_read_json(self.path)
        self.assertEqual(payload, loaded)

    @given(
        payload=st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=_JSON_LEAF,
            max_size=8,
        ),
        n=st.integers(min_value=2, max_value=10),
    )
    def test_last_write_wins(self, payload, n):
        from Storage.io import atomic_write_json, locked_read_json

        assume(json.dumps(payload))
        for _ in range(n):
            atomic_write_json(self.path, payload)
        loaded = locked_read_json(self.path)
        self.assertEqual(loaded, payload)


# ===========================================================================
# 5. reports.chart_generator — no crash on empty/sparse data
# ===========================================================================


class TestChartGeneratorRobustness(unittest.TestCase):
    """Chart functions must not raise on any valid analytics data shape."""

    @given(
        st.lists(
            st.fixed_dictionaries(
                {
                    "date": st.dates().map(lambda d: d.isoformat()),
                    "sleep_score": st.one_of(
                        st.none(), st.floats(min_value=0, max_value=100, allow_nan=False)
                    ),
                    "total_hours": st.one_of(
                        st.none(), st.floats(min_value=0, max_value=14, allow_nan=False)
                    ),
                    "quality_rating": st.one_of(st.none(), st.text(max_size=10)),
                }
            ),
            max_size=30,
        )
    )
    def test_sleep_trend_chart_never_raises(self, trend_data):
        try:
            from reports.chart_generator import sleep_trend_chart
        except RuntimeError:
            self.skipTest("plotly not installed")
        result = sleep_trend_chart(trend_data)
        self.assertIsInstance(result, dict)
        self.assertIn("data", result)

    @given(
        st.lists(
            st.fixed_dictionaries(
                {
                    "date": st.dates().map(lambda d: d.isoformat()),
                    "events": st.integers(min_value=0, max_value=1000),
                }
            ),
            max_size=30,
        )
    )
    def test_daily_activity_chart_never_raises(self, daily_data):
        try:
            from reports.chart_generator import daily_activity_chart
        except RuntimeError:
            self.skipTest("plotly not installed")
        result = daily_activity_chart(daily_data)
        self.assertIsInstance(result, dict)
        self.assertIn("data", result)

    @given(
        accepted=st.integers(min_value=0, max_value=500),
        declined=st.integers(min_value=0, max_value=500),
        days=st.integers(min_value=1, max_value=365),
    )
    def test_automation_effectiveness_chart_never_raises(self, accepted, declined, days):
        try:
            from reports.chart_generator import automation_effectiveness_chart
        except RuntimeError:
            self.skipTest("plotly not installed")
        total = accepted + declined
        rate = round(accepted / total * 100, 1) if total else 0
        data = {
            "total_accepted": accepted,
            "total_declined": declined,
            "acceptance_rate": rate,
            "period_days": days,
        }
        result = automation_effectiveness_chart(data)
        self.assertIsInstance(result, dict)
        self.assertIn("data", result)


if __name__ == "__main__":
    unittest.main()
