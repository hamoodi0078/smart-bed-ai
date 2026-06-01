"""Compatibility shim: notification tasks now run on the arq worker.

Old callers that used Celery-style `.delay()` should be migrated to enqueue
via the arq pool exposed on `request.app.state.arq`.  The helpers below
provide a synchronous enqueue path for legacy web_server.py call sites that
cannot be made async yet.

Migrate new code to:
    await arq_pool.enqueue_job("send_push_notification",
                               user_id=uid, notification_type=ntype, template_vars=tvars)
"""

from __future__ import annotations

from loguru import logger


def _get_arq_pool():
    """Return the arq pool from the running FastAPI app, or None."""
    try:
        from api.app_factory import app as _app
        return getattr(_app.state, "arq", None)
    except Exception:
        return None


def _enqueue(job_name: str, **kwargs) -> bool:
    """Fire-and-forget enqueue from a sync context.

    Uses asyncio.get_running_loop() (Python 3.7+, never deprecated) to detect
    whether we are inside an already-running event loop.  If yes, schedules the
    coroutine with ensure_future.  If no, uses asyncio.run() which creates a
    fresh event loop — safe on Python 3.10+ where get_event_loop() is deprecated
    when called with no running loop, and raises RuntimeError on 3.12+.
    """
    import asyncio

    pool = _get_arq_pool()
    if pool is None:
        logger.warning("notification_tasks: arq pool unavailable, dropping job={}", job_name)
        return False

    try:
        loop = asyncio.get_running_loop()
        # Already inside a running event loop (e.g. called from a sync route
        # handler that runs inside uvicorn's loop via run_in_executor).
        loop.create_task(pool.enqueue_job(job_name, **kwargs))
    except RuntimeError:
        # No running event loop — safe to use asyncio.run() (Python 3.7+).
        asyncio.run(pool.enqueue_job(job_name, **kwargs))
    return True


# ---------------------------------------------------------------------------
# Public API — same signatures as the old Celery tasks
# ---------------------------------------------------------------------------

def send_push_notification(user_id: str, notification_type: str, template_vars: dict) -> bool:
    ok = _enqueue("send_push_notification",
                  user_id=user_id, notification_type=notification_type,
                  template_vars=template_vars)
    logger.info("notification_tasks: enqueued push user={} type={}", user_id, notification_type)
    return ok


def send_whatsapp_notification(method: str, phone: str, user_id: str, extra: dict) -> bool:
    ok = _enqueue("send_whatsapp_notification",
                  method=method, phone=phone, user_id=user_id, extra=extra)
    logger.info("notification_tasks: enqueued whatsapp user={} method={}", user_id, method)
    return ok


def send_fcm_notification(user_id: str, notification_type: str, template_vars: dict) -> bool:
    ok = _enqueue("send_fcm_notification",
                  user_id=user_id, notification_type=notification_type,
                  template_vars=template_vars)
    logger.info("notification_tasks: enqueued FCM user={} type={}", user_id, notification_type)
    return ok


def send_weekly_report_notification(
    user_id: str, template_vars: dict | None = None
) -> bool:
    ok = _enqueue("send_weekly_report_notification",
                  user_id=user_id, template_vars=template_vars or {})
    logger.info("notification_tasks: enqueued weekly report user={}", user_id)
    return ok
