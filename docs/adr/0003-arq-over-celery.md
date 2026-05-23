# ADR 0003 — ARQ Over Celery for Background Jobs

**Status**: Accepted
**Date**: 2025-05

## Context

The project originally used Celery with a Redis broker for background tasks (email summaries, push notifications, report generation). However:

1. Celery is synchronous by design — tasks run in a forked worker process, not in an asyncio event loop.
2. The FastAPI backend and all DB access use asyncio (asyncpg, httpx). Celery workers cannot share these async resources.
3. Celery adds significant dependency weight (~15 transitive packages) and configuration complexity.
4. ARQ (Async Redis Queue) is asyncio-native, lightweight, and shares the same Redis instance.

## Decision

Replace Celery with ARQ as the sole job queue:

- `tasks/arq_app.py` defines `WorkerSettings` with lifecycle hooks (`on_startup`, `on_shutdown`).
- `tasks/arq_tasks.py` contains all async task functions.
- The ARQ worker shares async resources (asyncpg pool, pgvector index, httpx client) via the `ctx` dict.
- Docker compose runs `arq tasks.arq_app.WorkerSettings` for the worker service.
- `tasks/celery_app.py` is deprecated (stub file with DeprecationWarning).

## Consequences

- **Positive**: Single async stack — no sync/async impedance mismatch.
- **Positive**: Fewer dependencies (~50 MB less in Docker image).
- **Positive**: Worker shares DB pool with API — no redundant connections.
- **Negative**: ARQ has a smaller ecosystem than Celery (no Flower dashboard, fewer plugins).
- **Negative**: No built-in task routing by queue name (mitigated by ARQ's `queue_name` parameter).

## Redis Database Allocation

| DB | Purpose |
|----|---------|
| 0  | General cache / pub-sub |
| 2  | ARQ job queue (`ARQ_REDIS_URL`) |
