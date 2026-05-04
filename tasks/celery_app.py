"""Celery application instance for background task processing."""

from __future__ import annotations

from celery import Celery

from config import settings


def make_celery() -> Celery:
    app = Celery("danah_tasks")
    app.conf.update(
        broker_url=settings.celery_broker_url,
        result_backend=settings.celery_result_backend,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_routes={
            "tasks.notification_tasks.*": {"queue": "notifications"},
        },
    )
    app.autodiscover_tasks(["tasks"])
    return app


celery_app = make_celery()