"""arq async job functions.

Each function receives a ``ctx`` dict populated once per worker process by
``WorkerSettings.on_startup`` with shared async resources:

  ctx["async_db"]        AsyncDatabaseConnection (asyncpg pool)
  ctx["pgvector_index"]  PgVectorMemoryIndex  (None when PostgreSQL absent)
  ctx["http"]            httpx.AsyncClient

Enqueue from FastAPI:
    arq_pool = request.app.state.arq
    await arq_pool.enqueue_job("send_daily_email_summary", user_id="uid")

Start the worker:
    arq tasks.arq_app.WorkerSettings
"""

from __future__ import annotations

from loguru import logger


async def send_daily_email_summary(ctx: dict, *, user_id: str) -> bool:
    """Send a daily sleep summary email for one user, off the request thread."""
    try:
        from notifications.email_service import EmailService

        ok = EmailService().send_daily_summary_for_user(user_id)
        logger.info("arq: daily email sent user={} ok={}", user_id, ok)
        return ok
    except Exception as exc:
        logger.warning("arq: daily email failed user={} error={}", user_id, exc)
        raise


async def send_monthly_email_summary(
    ctx: dict,
    *,
    user_id: str,
    year: int,
    month: int,
) -> bool:
    """Send a monthly sleep summary email for one user, off the request thread."""
    try:
        from notifications.email_service import EmailService

        ok = EmailService().send_monthly_summary_for_user(user_id, int(year), int(month))
        logger.info(
            "arq: monthly email sent user={} year={} month={} ok={}",
            user_id,
            year,
            month,
            ok,
        )
        return ok
    except Exception as exc:
        logger.warning(
            "arq: monthly email failed user={} year={} month={} error={}",
            user_id,
            year,
            month,
            exc,
        )
        raise


async def embed_memory_entry(
    ctx: dict,
    *,
    doc_id: str,
    user_id: str,
    text: str,
    metadata: dict | None = None,
) -> bool:
    """Upsert a conversation turn into the pgvector memory index asynchronously.

    Uses the shared ``pgvector_index`` from ctx — no extra DB connection needed.
    Falls back gracefully when pgvector is unavailable.
    """
    index = ctx.get("pgvector_index")
    if index is None:
        logger.debug("arq: embed_memory_entry skipped — pgvector unavailable doc_id={}", doc_id)
        return False
    try:
        ok = await index.upsert(
            doc_id=doc_id,
            user_id=user_id,
            text=text,
            metadata=metadata or {},
        )
        logger.debug("arq: embed_memory_entry doc_id={} ok={}", doc_id, ok)
        return ok
    except Exception as exc:
        logger.warning("arq: embed_memory_entry failed doc_id={} error={}", doc_id, exc)
        raise


# ---------------------------------------------------------------------------
# Notification tasks (migrated from Celery)
# ---------------------------------------------------------------------------


async def send_push_notification(
    ctx: dict,
    *,
    user_id: str,
    notification_type: str,
    template_vars: dict,
) -> dict:
    """Send an Expo push notification off the request thread."""
    from notifications.expo_sender import ExpoPushSender
    from notifications.notification_types import NotificationType

    try:
        sender = ExpoPushSender()
        result = sender.send_to_user(
            user_id=user_id,
            notification_type=NotificationType(notification_type),
            template_vars=template_vars,
        )
        logger.info("arq: push notification sent user={} type={}", user_id, notification_type)
        return result
    except Exception as exc:
        logger.warning("arq: push notification failed user={} error={}", user_id, exc)
        raise


async def send_whatsapp_notification(
    ctx: dict,
    *,
    method: str,
    phone: str,
    user_id: str,
    extra: dict,
) -> dict:
    """Send a WhatsApp notification off the request thread.

    `method` is one of: 'dana_checkin', 'streak_message'.
    `extra` holds method-specific kwargs.
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
        logger.info("arq: WhatsApp notification sent user={} method={}", user_id, method)
        return result
    except Exception as exc:
        logger.warning("arq: WhatsApp notification failed user={} error={}", user_id, exc)
        raise


async def send_fcm_notification(
    ctx: dict,
    *,
    user_id: str,
    notification_type: str,
    template_vars: dict,
) -> dict:
    """Send a Firebase Cloud Messaging push notification off the request thread."""
    from notifications.fcm_sender import FcmSender
    from notifications.notification_types import NotificationType

    try:
        sender = FcmSender()
        result = sender.send_to_user(
            user_id=user_id,
            notification_type=NotificationType(notification_type),
            template_vars=template_vars,
        )
        logger.info("arq: FCM notification sent user={} type={}", user_id, notification_type)
        return result
    except Exception as exc:
        logger.warning("arq: FCM notification failed user={} error={}", user_id, exc)
        raise


async def send_weekly_report_notification(
    ctx: dict,
    *,
    user_id: str,
    template_vars: dict | None = None,
) -> dict:
    """Send a weekly sleep report push notification off the request thread."""
    from notifications.expo_sender import ExpoPushSender
    from notifications.notification_types import NotificationType

    try:
        sender = ExpoPushSender()
        result = sender.send_to_user(
            user_id=user_id,
            notification_type=NotificationType.WEEKLY_REPORT,
            template_vars=template_vars or {"user_name": user_id},
        )
        logger.info("arq: weekly report notification sent user={}", user_id)
        return result
    except Exception as exc:
        logger.warning("arq: weekly report notification failed user={} error={}", user_id, exc)
        raise
