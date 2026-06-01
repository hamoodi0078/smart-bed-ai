"""Application factory — assembles the FastAPI app with all middleware and routers.

Usage
-----
This is the single entry point for the application.  All routes are registered
here via include_router(); web_server.py is no longer mounted as a sub-app.
Individual routers still lazy-import handler functions from web_server.py as a
transitional step until each domain is fully extracted into its own service.

Deployment
----------
Development:
    uvicorn api.app_factory:app --reload

Production:
    gunicorn api.app_factory:app -w 4 -k uvicorn.workers.UvicornWorker
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


# ── Prometheus metrics (shared singleton — avoids duplicate-collector errors) ──
from core.metrics import REQUEST_COUNT, REQUEST_LATENCY, ERROR_COUNT


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────
@asynccontextmanager
async def _lifespan(app: FastAPI):
    from config.settings import settings
    from core.logger import logger

    # Validate production secrets on startup
    try:
        from config.settings import validate_production_secrets
        secret_warnings = validate_production_secrets()
        for w in secret_warnings:
            logger.warning("Secret config: %s", w)
    except Exception as exc:
        logger.warning("Secret validation error (non-fatal): %s", exc)

    # Service registry (automations, health monitor, etc.)
    try:
        from api.service_registry import initialize_services
        initialize_services(app)
    except Exception as exc:
        logger.warning("Service registry init error (non-fatal): %s", exc)

    # Sentry error tracking (must be initialised early so it catches startup errors)
    try:
        if settings.sentry_dsn:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
            from sentry_sdk.integrations.logging import LoggingIntegration
            sentry_sdk.init(
                dsn=settings.sentry_dsn,
                environment=settings.sentry_environment,
                release=settings.sentry_release or None,
                traces_sample_rate=settings.sentry_traces_sample_rate,
                profiles_sample_rate=settings.sentry_profiles_sample_rate,
                integrations=[
                    FastApiIntegration(),
                    SqlalchemyIntegration(),
                    LoggingIntegration(level=None, event_level=None),
                ],
                send_default_pii=False,
            )
            logger.info("Sentry initialized (env=%s)", settings.sentry_environment)
    except Exception as exc:
        logger.warning("Sentry init skipped: %s", exc)

    # Async PostgreSQL pool
    try:
        from database import AsyncDatabaseConnection
        _async_db = AsyncDatabaseConnection()
        await _async_db.initialize()
        app.state.async_db = _async_db
        # Expose session factory so get_db_session() dependency works
        app.state.db_session_factory = _async_db._session_factory
    except Exception as exc:
        logger.warning("Async DB init skipped (non-fatal): %s", exc)
        app.state.async_db = None
        app.state.db_session_factory = None

    # pgvector memory index
    try:
        from ai.pgvector_memory_index import PgVectorMemoryIndex
        if app.state.async_db is not None:
            app.state.pgvector_index = PgVectorMemoryIndex(app.state.async_db)
        else:
            app.state.pgvector_index = None
    except Exception as exc:
        logger.warning("PgVectorMemoryIndex init skipped: %s", exc)
        app.state.pgvector_index = None

    # arq job queue
    try:
        from arq import create_pool
        from arq.connections import RedisSettings
        app.state.arq = await create_pool(RedisSettings.from_dsn(settings.arq_redis_url))
    except Exception as exc:
        logger.warning("arq pool init skipped: %s", exc)
        app.state.arq = None

    # Firebase FCM
    try:
        from notifications.fcm_sender import FcmSender, initialize_firebase
        firebase_ok = initialize_firebase(
            credentials_path=settings.firebase_credentials_path,
            credentials_json=settings.firebase_credentials_json,
        )
        app.state.fcm_sender = FcmSender() if firebase_ok else None
    except Exception as exc:
        logger.warning("Firebase init skipped: %s", exc)
        app.state.fcm_sender = None

    logger.info("Danah API ready")
    yield

    # Graceful shutdown
    if getattr(app.state, "async_db", None):
        try:
            await app.state.async_db.close()
        except Exception as exc:
            logger.warning("Async DB shutdown error: %s", exc)
    if getattr(app.state, "arq", None):
        try:
            await app.state.arq.close()
        except Exception as exc:
            logger.warning("arq pool shutdown error: %s", exc)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    from config.settings import settings

    _cors_raw = str(settings.web_allowed_origins_raw or "http://127.0.0.1:8000,http://localhost:8000")
    allowed_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
    allowed_origin_regex = str(settings.web_allowed_origin_regex or "").strip() or None

    application = FastAPI(
        title="Danah Smart Bed API",
        version="2.0.0",
        description="AI-powered smart bed — voice assistant, Islamic features, sleep science.",
        lifespan=_lifespan,
        docs_url="/docs" if os.getenv("DANAH_ENV", "development") != "production" else None,
        redoc_url="/redoc" if os.getenv("DANAH_ENV", "development") != "production" else None,
    )

    # ── Middleware stack (order matters: innermost runs last) ─────────────────

    # CORS origin validation — crash early on misconfiguration
    if "*" in allowed_origins:
        is_production = os.getenv("DANAH_ENV", "development").lower() == "production"
        if is_production:
            raise RuntimeError(
                "CORS misconfiguration: WEB_ALLOWED_ORIGINS contains '*' wildcard in production. "
                "Specify explicit origin URLs."
            )
        import warnings as _warnings
        _warnings.warn(
            "CORS: allow_origins=['*'] detected — this is unsafe for production.",
            stacklevel=2,
        )
    _allow_credentials = bool(allowed_origins) and "*" not in allowed_origins

    # Trace ID — inject X-Trace-ID / X-Request-ID on every request
    from api.middleware.trace_id import TraceIDMiddleware
    application.add_middleware(TraceIDMiddleware)

    # Rate limiting — hard import: app must not start without this protection
    from api.middleware.rate_limiter import RateLimitMiddleware
    application.add_middleware(RateLimitMiddleware)

    # Security headers — applied to every response
    from api.middleware.security_headers import SecurityHeadersMiddleware
    application.add_middleware(SecurityHeadersMiddleware)

    # slowapi per-route limiter — must be on app.state before routes are hit
    try:
        from slowapi import _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded
        from api.limiter import limiter
        application.state.limiter = limiter
        application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    except ImportError:
        pass

    # CORS
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_origin_regex=allowed_origin_regex,
        allow_credentials=_allow_credentials,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Trace-ID", "X-Request-ID"],
    )

    # ── Exception handlers ────────────────────────────────────────────────────
    from fastapi import Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "error": "validation_error",
                "detail": exc.errors(),
            },
        )

    @application.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        from core.logger import logger
        logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(status_code=500, content={"ok": False, "error": "internal_server_error"})

    # ── Prometheus request instrumentation ───────────────────────────────────
    import time
    from starlette.middleware.base import BaseHTTPMiddleware

    class _MetricsMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            t0 = time.perf_counter()
            response = await call_next(request)
            elapsed = time.perf_counter() - t0
            path = request.url.path
            method = request.method
            status = str(response.status_code)
            REQUEST_COUNT.labels(method=method, path=path, status_code=status).inc()
            REQUEST_LATENCY.labels(method=method, path=path).observe(elapsed)
            if response.status_code >= 400:
                ERROR_COUNT.labels(method=method, path=path, status_code=status).inc()
            return response

    application.add_middleware(_MetricsMiddleware)

    # ── Routers (migrated domains) ────────────────────────────────────────────
    from api.routers.health import router as health_router
    from api.routers.metrics import router as metrics_router
    from api.routers.islamic import router as islamic_router

    application.include_router(health_router)
    application.include_router(metrics_router)
    application.include_router(islamic_router)

    # Automation router (canonical — wraps legacy api/automation_routes.py internally)
    try:
        from api.routers.automations import router as automation_router
        application.include_router(automation_router)
    except ImportError:
        pass

    # Migrated routers (Sprint 1)
    from api.routers.auth import router as auth_router
    from api.routers.alarms import router as alarms_router
    from api.routers.sleep import router as sleep_router
    from api.routers.scenes import router as scenes_router
    from api.routers.profile import router as profile_router
    application.include_router(auth_router)
    application.include_router(alarms_router)
    application.include_router(sleep_router)
    application.include_router(scenes_router)
    application.include_router(profile_router)

    # Migrated routers (Sprint 2)
    from api.routers.devices import router as devices_router
    from api.routers.subscriptions import router as subscriptions_router
    from api.routers.chat import router as chat_router
    from api.routers.spotify import router as spotify_router
    from api.routers.admin import router as admin_router, public_router as admin_public_router
    from api.routers.reports import router as reports_router
    from api.routers.integrations import router as integrations_router
    application.include_router(devices_router)
    application.include_router(subscriptions_router)
    application.include_router(chat_router)
    application.include_router(spotify_router)
    application.include_router(admin_public_router)
    application.include_router(admin_router)
    application.include_router(reports_router)
    application.include_router(integrations_router)

    # Migrated routers (Sprint 3 — final legacy mount removal)
    from api.routers.pages import router as pages_router
    from api.routers.actions import router as actions_router
    from api.routers.mobile_features import router as mobile_features_router
    application.include_router(pages_router)
    application.include_router(actions_router)
    application.include_router(mobile_features_router)

    # Domains that previously only existed in master_api.py
    try:
        from dana.dana_api import router as dana_router
        application.include_router(dana_router)
    except ImportError as exc:
        from core.logger import logger
        logger.warning("dana_api unavailable (skipped): %s", exc)

    try:
        from guest_mode.guest_api import router as guest_router
        application.include_router(guest_router)
    except ImportError as exc:
        from core.logger import logger
        logger.warning("guest_api unavailable (skipped): %s", exc)

    try:
        from qr_code.qr_api import router as qr_router
        application.include_router(qr_router)
    except ImportError as exc:
        from core.logger import logger
        logger.warning("qr_api unavailable (skipped): %s", exc)

    # Monitoring / diagnostics router
    try:
        from api.monitoring import router as monitoring_router
        application.include_router(monitoring_router)
    except ImportError as exc:
        from core.logger import logger
        logger.warning("monitoring router unavailable (skipped): %s", exc)

    # OpenTelemetry FastAPI auto-instrumentation (after all routes are registered)
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor().instrument_app(application)
    except ImportError:
        pass

    return application


# Module-level app instance for uvicorn/gunicorn
app = create_app()
