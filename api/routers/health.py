"""Health-check endpoints — extracted from web_server.py.

These are fully self-contained: no profile state, no user auth.
"""

from __future__ import annotations

import shutil
from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from config.settings import settings

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"ok": True, "service": "web_runtime"}


@router.get("/readyz")
def readyz() -> dict[str, Any]:
    """Readiness probe — verifies DB and Redis are reachable."""
    checks: dict[str, Any] = {}
    all_ok = True

    # Database
    try:
        from database.connection import DatabaseConnection

        db_conn = DatabaseConnection()
        db_ok = db_conn.health_check()
        checks["database"] = {"ok": db_ok}
        if not db_ok:
            all_ok = False
    except Exception as exc:
        checks["database"] = {"ok": False, "error": type(exc).__name__}
        all_ok = False

    # Redis
    try:
        import redis as _redis

        r = _redis.from_url(settings.celery_broker_url, socket_connect_timeout=2)
        r.ping()
        checks["redis"] = {"ok": True}
    except Exception as exc:
        checks["redis"] = {"ok": False, "error": type(exc).__name__}
        all_ok = False

    checks["ok"] = all_ok
    if not all_ok:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content=checks)
    return checks


@router.get("/healthz/detailed")
def healthz_detailed() -> dict[str, Any]:
    checks: dict[str, Any] = {"service": "web_runtime"}

    try:
        from database.connection import DatabaseConnection

        db_conn = DatabaseConnection()
        checks["database"] = {"ok": db_conn.health_check(), "version": db_conn.schema_version()}
    except Exception as exc:
        checks["database"] = {"ok": False, "error": type(exc).__name__}

    try:
        disk = shutil.disk_usage("/")
        checks["disk"] = {
            "total_gb": round(disk.total / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
            "used_pct": round((disk.used / disk.total) * 100, 1),
        }
    except Exception:
        checks["disk"] = {"ok": False}

    checks["deepgram_configured"] = bool(str(settings.deepgram_api_key or "").strip())
    checks["ok"] = checks.get("database", {}).get("ok", False)
    return checks
