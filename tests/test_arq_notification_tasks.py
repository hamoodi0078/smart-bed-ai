"""Tests for arq notification task coroutines.

All tasks are called directly (not via arq worker) with a minimal ctx dict.
External senders (ExpoPushSender, WhatsAppNotifier, FcmSender) are mocked.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


CTX: dict = {}


class TestSendPushNotification(unittest.TestCase):
    def test_sends_to_user_and_returns_result(self):
        from tasks.arq_tasks import send_push_notification

        mock_result = {"sent": True, "token": "ExpoToken[xxx]"}
        mock_sender = MagicMock()
        mock_sender.send_to_user.return_value = mock_result

        with patch("notifications.expo_sender.ExpoPushSender", return_value=mock_sender):
            result = _run(send_push_notification(
                CTX,
                user_id="u-1",
                notification_type="dana_checkin",
                template_vars={"days": 3, "user_name": "u-1"},
            ))

        self.assertEqual(result, mock_result)
        mock_sender.send_to_user.assert_called_once()

    def test_raises_on_sender_exception(self):
        from tasks.arq_tasks import send_push_notification

        mock_sender = MagicMock()
        mock_sender.send_to_user.side_effect = RuntimeError("network error")

        with patch("notifications.expo_sender.ExpoPushSender", return_value=mock_sender):
            with self.assertRaises(RuntimeError):
                _run(send_push_notification(
                    CTX,
                    user_id="u-2",
                    notification_type="dana_checkin",
                    template_vars={},
                ))


class TestSendWhatsappNotification(unittest.TestCase):
    def test_dana_checkin_method(self):
        from tasks.arq_tasks import send_whatsapp_notification

        mock_notifier = MagicMock()
        mock_notifier.send_dana_checkin.return_value = {"sent": True}

        with patch("notifications.whatsapp_notifier.WhatsAppNotifier", return_value=mock_notifier):
            result = _run(send_whatsapp_notification(
                CTX,
                method="dana_checkin",
                phone="+96511111111",
                user_id="u-3",
                extra={"days_inactive": 5},
            ))

        self.assertEqual(result, {"sent": True})
        mock_notifier.send_dana_checkin.assert_called_once_with("+96511111111", "u-3", 5)

    def test_streak_message_method(self):
        from tasks.arq_tasks import send_whatsapp_notification

        mock_notifier = MagicMock()
        mock_notifier.send_streak_message.return_value = {"sent": True}

        with patch("notifications.whatsapp_notifier.WhatsAppNotifier", return_value=mock_notifier):
            result = _run(send_whatsapp_notification(
                CTX,
                method="streak_message",
                phone="+96511111111",
                user_id="u-4",
                extra={"streak_days": 7},
            ))

        mock_notifier.send_streak_message.assert_called_once_with("+96511111111", "u-4", 7)

    def test_unknown_method_returns_not_sent(self):
        from tasks.arq_tasks import send_whatsapp_notification

        mock_notifier = MagicMock()

        with patch("notifications.whatsapp_notifier.WhatsAppNotifier", return_value=mock_notifier):
            result = _run(send_whatsapp_notification(
                CTX,
                method="unknown_method",
                phone="+96511111111",
                user_id="u-5",
                extra={},
            ))

        self.assertFalse(result["sent"])
        self.assertIn("unknown_method", result["reason"])


class TestSendFcmNotification(unittest.TestCase):
    def test_sends_and_returns_result(self):
        from tasks.arq_tasks import send_fcm_notification

        mock_result = {"sent": True, "message_id": "fcm-msg-1"}
        mock_sender = MagicMock()
        mock_sender.send_to_user.return_value = mock_result

        with patch("notifications.fcm_sender.FcmSender", return_value=mock_sender):
            result = _run(send_fcm_notification(
                CTX,
                user_id="u-6",
                notification_type="weekly_report",
                template_vars={"user_name": "u-6"},
            ))

        self.assertEqual(result, mock_result)

    def test_raises_on_sender_exception(self):
        from tasks.arq_tasks import send_fcm_notification

        mock_sender = MagicMock()
        mock_sender.send_to_user.side_effect = ConnectionError("FCM unreachable")

        with patch("notifications.fcm_sender.FcmSender", return_value=mock_sender):
            with self.assertRaises(ConnectionError):
                _run(send_fcm_notification(
                    CTX,
                    user_id="u-7",
                    notification_type="dana_checkin",
                    template_vars={},
                ))


class TestSendWeeklyReportNotification(unittest.TestCase):
    def test_sends_weekly_report(self):
        from tasks.arq_tasks import send_weekly_report_notification

        mock_result = {"sent": True}
        mock_sender = MagicMock()
        mock_sender.send_to_user.return_value = mock_result

        with patch("notifications.expo_sender.ExpoPushSender", return_value=mock_sender):
            result = _run(send_weekly_report_notification(
                CTX,
                user_id="u-8",
                template_vars={"user_name": "u-8"},
            ))

        self.assertEqual(result, mock_result)

    def test_uses_user_id_as_default_name_when_no_template_vars(self):
        from tasks.arq_tasks import send_weekly_report_notification

        mock_sender = MagicMock()
        mock_sender.send_to_user.return_value = {"sent": True}

        with patch("notifications.expo_sender.ExpoPushSender", return_value=mock_sender):
            _run(send_weekly_report_notification(CTX, user_id="u-9"))

        call_kwargs = mock_sender.send_to_user.call_args[1]
        self.assertEqual(call_kwargs["template_vars"]["user_name"], "u-9")


class TestNotificationSchedulerShim(unittest.TestCase):
    """Verify the sync shim in notification_tasks.py doesn't crash and returns bool."""

    def test_send_push_notification_returns_bool(self):
        from tasks.notification_tasks import send_push_notification

        with patch("tasks.notification_tasks._get_arq_pool", return_value=None):
            result = send_push_notification(
                user_id="u-10",
                notification_type="dana_checkin",
                template_vars={"days": 1},
            )

        self.assertIsInstance(result, bool)

    def test_send_whatsapp_notification_returns_bool(self):
        from tasks.notification_tasks import send_whatsapp_notification

        with patch("tasks.notification_tasks._get_arq_pool", return_value=None):
            result = send_whatsapp_notification(
                method="dana_checkin",
                phone="+96511111111",
                user_id="u-11",
                extra={},
            )

        self.assertIsInstance(result, bool)


if __name__ == "__main__":
    unittest.main()
