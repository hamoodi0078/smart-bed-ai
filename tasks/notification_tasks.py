"""Celery tasks for sending notifications without blocking request handlers."""

from __future__ import annotations

from celery import shared_task
from loguru import logger

from tasks.celery_app import celery_app


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="tasks.notification_tasks.send_push_notification",
)
def send_push_notification(
    self,
    user_id: str,
    notification_type: str,
    template_vars: dict,
) -> dict:
    """Send an Expo push notification in a background worker with retry."""
    from notifications.expo_sender import ExpoPushSender
    from notifications.notification_types import NotificationType

    try:
        sender = ExpoPushSender()
        result = sender.send_to_user(
            user_id=user_id,
            notification_type=NotificationType(notification_type),
            template_vars=template_vars,
        )
        logger.info("Push notification sent: user={} type={}", user_id, notification_type)
        return result
    except Exception as exc:
        logger.warning(
            "Push notification failed (attempt {}/{}): user={} error={}",
            self.request.retries + 1, self.max_retries + 1, user_id, exc,
        )
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="tasks.notification_tasks.send_whatsapp_notification",
)
def send_whatsapp_notification(
    self,
    method: str,
    phone: str,
    user_id: str,
    extra: dict,
) -> dict:
    """Send a WhatsApp notification in a background worker with retry.

    `method` is one of: 'dana_checkin', 'streak_message'.
    `extra` holds method-specific kwargs (e.g. days_inactive, streak_days).
    """
    from notifications.whatsapp_notifier import WhatsAppNotifier

    try:
        notifier = WhatsAppNotifier()
        if method == "dana_checkin":
            result = notifier.send_dana_checkin(phone, user_id, int(extra.get("days_inactive", 0)))
        elif method == "streak_message":
            result = notifier.send_streak_message(phone, user_id, int(extra.get("streak_days", 0)))
        else:
            return {"sent": False, "reason": f"unknown_method:{method}"}
        logger.info("WhatsApp notification sent: user={} method={}", user_id, method)
        return result
    except Exception as exc:
        logger.warning(
            "WhatsApp notification failed (attempt {}/{}): user={} error={}",
            self.request.retries + 1, self.max_retries + 1, user_id, exc,
        )
        raise self.retry(exc=exc)