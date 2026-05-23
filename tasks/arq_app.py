"""arq worker configuration and lifecycle hooks.

arq is the asyncio-native job queue — tasks run inside an asyncio event loop
and share long-lived async resources (asyncpg pool, pgvector index, httpx
client) injected via the ``ctx`` dict by ``on_startup``.

Start the worker:
    arq tasks.arq_app.WorkerSettings

Redis database allocation:
    db 0 — Celery broker
    db 1 — Celery result backend
    db 2 — arq jobs  (ARQ_REDIS_URL, default redis://localhost:6379/2)
"""

from __future__ import annotations

import httpx
from arq.connections import RedisSettings
from loguru import logger

from tasks.arq_tasks import (
    embed_memory_entry,
    send_daily_email_summary,
    send_fcm_notification,
    send_monthly_email_summary,
    send_push_notification,
    send_weekly_report_notification,
    send_whatsapp_notification,
)


def _redis_settings() -> RedisSettings:
    from config import settings
    return RedisSettings.from_dsn(settings.arq_redis_url)


# ---------------------------------------------------------------------------
# Worker lifecycle
# ---------------------------------------------------------------------------

async def startup(ctx: dict) -> None:
    """Initialise shared async resources once per worker process."""
    from database.connection import AsyncDatabaseConnection
    from ai.pgvector_memory_index import PgVectorMemoryIndex

    try:
        async_db = AsyncDatabaseConnection()
        await async_db.initialize()
        ctx["async_db"] = async_db
        ctx["pgvector_index"] = PgVectorMemoryIndex(async_db)
        logger.info("arq worker: async DB connected")
    except Exception as exc:
        logger.warning("arq worker: async DB unavailable (non-fatal) — {}", exc)
        ctx["async_db"] = None
        ctx["pgvector_index"] = None

    ctx["http"] = httpx.AsyncClient(timeout=20.0)
    logger.info("arq worker: startup complete")


async def shutdown(ctx: dict) -> None:
    """Drain shared resources on worker shutdown."""
    async_db = ctx.get("async_db")
    if async_db is not None:
        await async_db.close()
        logger.info("arq worker: async DB closed")

    http_client = ctx.get("http")
    if http_client is not None:
        await http_client.aclose()
    logger.info("arq worker: shutdown complete")


# ---------------------------------------------------------------------------
# Worker settings
# ---------------------------------------------------------------------------

class WorkerSettings:
    functions = [
        send_daily_email_summary,
        send_monthly_email_summary,
        embed_memory_entry,
        send_push_notification,
        send_whatsapp_notification,
        send_fcm_notification,
        send_weekly_report_notification,
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    max_jobs = 10
    job_timeout = 300       # seconds — max runtime per job before it is cancelled
    keep_result = 3600      # seconds — keep job result key in Redis
    retry_jobs = True
    max_tries = 3
    queue_name = "arq:default"