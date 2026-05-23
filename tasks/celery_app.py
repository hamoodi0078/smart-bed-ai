"""Celery application instance — **DEPRECATED**.

Celery has been replaced by ARQ (``tasks/arq_app.py``) as the sole async job
queue.  This file is kept only so that imports referencing ``celery_app`` do
not crash at import time.  Remove this file once all call-sites are confirmed
to use ARQ instead.

To run the async worker:
    arq tasks.arq_app.WorkerSettings
"""

from __future__ import annotations

import warnings

warnings.warn(
    "tasks.celery_app is deprecated — use arq (tasks.arq_app.WorkerSettings) instead.",
    DeprecationWarning,
    stacklevel=2,
)

celery_app = None  # Stub — prevents AttributeError on import