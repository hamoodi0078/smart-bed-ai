import os
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from database import DatabaseConnection
from database.models import Event
from database.repositories import EventRepository, SleepSessionRepository
from notifications import build_daily_summary, build_monthly_summary


class TestNotificationSummaries(unittest.TestCase):
    def setUp(self):
        self._old_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = "sqlite://"
        self.db = DatabaseConnection()
        self.event_repo = EventRepository(self.db)
        self.sleep_repo = SleepSessionRepository(self.db)
        self.user_id = "user-123"
        self.yesterday = date(2026, 3, 7)
        self.today_utc = datetime(2026, 3, 8, 9, 0, tzinfo=timezone.utc)

    def tearDown(self):
        if self._old_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self._old_database_url

    def _insert_event(
        self, event_type: str, timestamp: datetime, user_id: str | None = None
    ) -> None:
        with self.db.get_session() as session:
            session.add(
                Event(
                    user_id=user_id or self.user_id,
                    event_type=event_type,
                    timestamp=timestamp,
                )
            )

    def test_build_daily_summary_no_events_returns_zero_counts(self):
        with patch("notifications.summaries.utcnow", return_value=self.today_utc):
            payload = build_daily_summary(
                self.user_id,
                event_repo=self.event_repo,
                sleep_repo=self.sleep_repo,
            )

        metadata = payload["metadata"]
        self.assertEqual(metadata["date"], "2026-03-07")
        self.assertEqual(metadata["scenes_used_count"], 0)
        self.assertEqual(metadata["winddowns_completed"], 0)
        self.assertEqual(metadata["automations_fired"], 0)
        self.assertFalse(metadata["has_sleep_session"])
        self.assertIn("No sleep activity recorded last night.", payload["plain_text"])

    def test_build_daily_summary_counts_scenes_winddowns_and_automations(self):
        self._insert_event("sceneactivated", datetime(2026, 3, 7, 21, 0, tzinfo=timezone.utc))
        self._insert_event("sceneactivated", datetime(2026, 3, 7, 22, 0, tzinfo=timezone.utc))
        self._insert_event("winddownstarted", datetime(2026, 3, 7, 22, 30, tzinfo=timezone.utc))
        self._insert_event("automationfired", datetime(2026, 3, 7, 23, 0, tzinfo=timezone.utc))
        self._insert_event("automationfired", datetime(2026, 3, 7, 23, 10, tzinfo=timezone.utc))
        self._insert_event("automationfired", datetime(2026, 3, 7, 23, 20, tzinfo=timezone.utc))
        self._insert_event("sceneactivated", datetime(2026, 3, 6, 20, 0, tzinfo=timezone.utc))

        with patch("notifications.summaries.utcnow", return_value=self.today_utc):
            payload = build_daily_summary(
                self.user_id,
                event_repo=self.event_repo,
                sleep_repo=self.sleep_repo,
            )

        metadata = payload["metadata"]
        self.assertEqual(metadata["scenes_used_count"], 2)
        self.assertEqual(metadata["winddowns_completed"], 1)
        self.assertEqual(metadata["automations_fired"], 3)
        self.assertIn("You followed your wind-down plan. Great job.", payload["plain_text"])

    def test_build_daily_summary_uses_sleep_session_values_when_present(self):
        self.sleep_repo.create_or_update_session(
            self.user_id,
            self.yesterday,
            total_sleep_minutes=420,
            restlessness_score=35.5,
        )

        with patch("notifications.summaries.utcnow", return_value=self.today_utc):
            payload = build_daily_summary(
                self.user_id,
                event_repo=self.event_repo,
                sleep_repo=self.sleep_repo,
            )

        self.assertTrue(payload["metadata"]["has_sleep_session"])
        self.assertIn("420 min", payload["plain_text"])
        self.assertIn("35.5", payload["plain_text"])
        self.assertIn("420 min", payload["whatsapp_text"])
        self.assertIn("35.5", payload["whatsapp_text"])

    def test_build_monthly_summary_computes_basic_aggregates(self):
        self.sleep_repo.create_or_update_session(
            self.user_id,
            date(2026, 3, 1),
            total_sleep_minutes=420,
            restlessness_score=35.0,
            winddowns_completed=1,
        )
        self.sleep_repo.create_or_update_session(
            self.user_id,
            date(2026, 3, 2),
            total_sleep_minutes=390,
            restlessness_score=45.0,
            winddowns_completed=2,
        )
        self.sleep_repo.create_or_update_session(
            self.user_id,
            date(2026, 3, 3),
            total_sleep_minutes=None,
            restlessness_score=None,
            winddowns_completed=1,
        )

        payload = build_monthly_summary(
            self.user_id,
            2026,
            3,
            event_repo=self.event_repo,
            sleep_repo=self.sleep_repo,
        )

        metadata = payload["metadata"]
        self.assertEqual(metadata["nights_tracked"], 3)
        self.assertEqual(metadata["average_sleep_minutes"], 405)
        self.assertEqual(metadata["average_restlessness"], 40.0)
        self.assertEqual(metadata["winddowns_completed_total"], 4)

    def test_build_monthly_summary_handles_empty_month_gracefully(self):
        payload = build_monthly_summary(
            self.user_id,
            2026,
            2,
            event_repo=self.event_repo,
            sleep_repo=self.sleep_repo,
        )

        metadata = payload["metadata"]
        self.assertEqual(metadata["nights_tracked"], 0)
        self.assertIsNone(metadata["average_sleep_minutes"])
        self.assertIsNone(metadata["average_restlessness"])
        self.assertEqual(metadata["winddowns_completed_total"], 0)
        self.assertIn("Not enough data this month", payload["plain_text"])

    def test_build_monthly_summary_highlight_changes_with_good_restlessness(self):
        for day in range(1, 21):
            self.sleep_repo.create_or_update_session(
                self.user_id,
                date(2026, 1, day),
                total_sleep_minutes=410,
                restlessness_score=35.0,
                winddowns_completed=1,
            )

        payload = build_monthly_summary(
            self.user_id,
            2026,
            1,
            event_repo=self.event_repo,
            sleep_repo=self.sleep_repo,
        )

        self.assertIn("Your sleep consistency this month was strong.", payload["plain_text"])
        self.assertIn("Your sleep consistency this month was strong.", payload["whatsapp_text"])


if __name__ == "__main__":
    unittest.main()
