import os
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from database import DatabaseConnection, EventRepository, SleepSessionRepository, UserRepository
from database.models import Event
from notifications.email_service import EmailService


class _FakeResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


class TestEmailService(unittest.TestCase):
    def setUp(self):
        self._old_database_url = os.environ.get("DATABASE_URL")
        self._old_sendgrid_api_key = os.environ.get("SENDGRID_API_KEY")
        self._old_email_from = os.environ.get("EMAIL_FROM")

        os.environ["DATABASE_URL"] = "sqlite://"
        os.environ["SENDGRID_API_KEY"] = "sg.test-key"
        os.environ["EMAIL_FROM"] = "noreply@manues.example"

        self.db = DatabaseConnection()
        self.user_repo = UserRepository(db=self.db)
        self.event_repo = EventRepository(db=self.db)
        self.sleep_repo = SleepSessionRepository(db=self.db)

    def tearDown(self):
        if self._old_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self._old_database_url

        if self._old_sendgrid_api_key is None:
            os.environ.pop("SENDGRID_API_KEY", None)
        else:
            os.environ["SENDGRID_API_KEY"] = self._old_sendgrid_api_key

        if self._old_email_from is None:
            os.environ.pop("EMAIL_FROM", None)
        else:
            os.environ["EMAIL_FROM"] = self._old_email_from

    def test_send_daily_summary_for_user_skips_when_user_missing_email(self):
        user = self.user_repo.create_user("", "hash", "No Email User")
        service = EmailService(db=self.db)

        with patch("notifications.email_service.requests.post") as mocked_post:
            result = service.send_daily_summary_for_user(user.id)

        self.assertFalse(result)
        mocked_post.assert_not_called()

    def test_send_daily_summary_for_user_calls_sendgrid_with_expected_payload(self):
        user = self.user_repo.create_user("daily@example.com", "hash", "Daily User")
        fixed_now = datetime(2026, 3, 8, 9, 0, tzinfo=timezone.utc)

        with self.db.get_session() as session:
            session.add(
                Event(
                    user_id=user.id,
                    event_type="sceneactivated",
                    timestamp=datetime(2026, 3, 7, 22, 0, tzinfo=timezone.utc),
                )
            )
        self.sleep_repo.create_or_update_session(
            user.id,
            date(2026, 3, 7),
            total_sleep_minutes=410,
            restlessness_score=31.2,
            winddowns_completed=1,
        )

        service = EmailService(db=self.db)
        with patch("notifications.summaries.utcnow", return_value=fixed_now):
            with patch(
                "notifications.email_service.requests.post",
                return_value=_FakeResponse(202, "accepted"),
            ) as mocked_post:
                result = service.send_daily_summary_for_user(user.id)

        self.assertTrue(result)
        mocked_post.assert_called_once()
        args, kwargs = mocked_post.call_args
        self.assertEqual(args[0], "https://api.sendgrid.com/v3/mail/send")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer sg.test-key")
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")
        payload = kwargs["json"]
        self.assertEqual(payload["personalizations"][0]["to"][0]["email"], "daily@example.com")
        self.assertEqual(payload["subject"], "Your Manues daily sleep summary")
        self.assertEqual(payload["content"][0]["type"], "text/plain")
        self.assertTrue(str(payload["content"][0]["value"]).strip())

    def test_send_monthly_summary_for_user_handles_non_2xx_response_gracefully(self):
        user = self.user_repo.create_user("monthly@example.com", "hash", "Monthly User")
        service = EmailService(db=self.db)

        with patch(
            "notifications.email_service.requests.post",
            return_value=_FakeResponse(500, "send failed"),
        ):
            result = service.send_monthly_summary_for_user(user.id, 2026, 3)

        self.assertFalse(result)

    def test_send_daily_summaries_for_all_users_counts_successes(self):
        first = self.user_repo.create_user("first@example.com", "hash", "First")
        self.user_repo.create_user("", "hash", "No Email")
        third = self.user_repo.create_user("third@example.com", "hash", "Third")
        service = EmailService(db=self.db)

        with patch.object(service, "send_daily_summary_for_user", side_effect=[True, False]) as mocked_sender:
            sent_count = service.send_daily_summaries_for_all_users()

        self.assertEqual(sent_count, 1)
        self.assertEqual(mocked_sender.call_count, 2)
        called_ids = {call.args[0] for call in mocked_sender.call_args_list}
        self.assertEqual(called_ids, {first.id, third.id})

    def test_send_monthly_summaries_for_all_users_counts_successes(self):
        first = self.user_repo.create_user("a@example.com", "hash", "First")
        self.user_repo.create_user("", "hash", "No Email")
        third = self.user_repo.create_user("b@example.com", "hash", "Third")
        service = EmailService(db=self.db)

        with patch.object(service, "send_monthly_summary_for_user", side_effect=[True, False]) as mocked_sender:
            sent_count = service.send_monthly_summaries_for_all_users(2026, 2)

        self.assertEqual(sent_count, 1)
        self.assertEqual(mocked_sender.call_count, 2)
        called_args = [call.args for call in mocked_sender.call_args_list]
        self.assertEqual({args[0] for args in called_args}, {first.id, third.id})
        self.assertTrue(all(args[1] == 2026 and args[2] == 2 for args in called_args))


if __name__ == "__main__":
    unittest.main()
