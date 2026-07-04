from __future__ import annotations

import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from api.limiter import limiter
from api.middleware.error_handler import ErrorHandlerMiddleware
from core.tracing import setup_tracing
from api.middleware.rate_limiter import RateLimitMiddleware
from api.middleware.trace_id import TraceIDMiddleware
from api.models.responses import HealthStatus, SystemStatus, SuccessResponse
from api.monitoring import router as monitoring_router
from config import settings
from core.errors import BedError, bed_error_to_response, error_response, INTERNAL_ERROR
from core.service_registry import ServiceRegistry
from dana.dana_api import router as dana_router
from guest_mode.guest_api import router as guest_router
from islamic_mode.islamic_api import router as islamic_router
from master_controller import MasterController
from qr_code.qr_api import router as qr_router
from spotify.spotify_api import router as spotify_router

_app_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown."""
    # Startup
    logger.info("Starting Danah Abu Halifa API...")

    # Initialize service registry
    registry = ServiceRegistry()
    app.state.services = registry
    app.state.user_profile = {}

    # OpenTelemetry tracing
    setup_tracing(app)

    logger.info("API startup complete")

    yield

    # Shutdown
    logger.info("Shutting down Danah Abu Halifa API...")
    registry.clear()
    logger.info("API shutdown complete")


app = FastAPI(
    title="Danah Abu Halifa",
    description="Smart Bed AI with Dana personality assistant",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Wire slowapi: state lets the Limiter find itself via request.app.state.limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add middleware stack (order matters - first added is outermost)
app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(TraceIDMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)
_master_allowed_origins = [
    o.strip() for o in settings.web_allowed_origins_raw.split(",") if o.strip()
]
_master_cors_credentials = bool(_master_allowed_origins) and "*" not in _master_allowed_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_master_allowed_origins,
    allow_credentials=_master_cors_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Trace-ID", "X-Request-ID"],
)

app.include_router(monitoring_router)
app.include_router(dana_router)
app.include_router(islamic_router)
app.include_router(spotify_router)
app.include_router(guest_router)
app.include_router(qr_router)


@app.exception_handler(BedError)
async def bed_error_handler(request: Request, exc: BedError):
    """Handle BedError exceptions globally."""
    trace_id = getattr(request.state, "trace_id", "")
    logger.warning("BedError: {} trace_id={}", exc.message, trace_id)
    return bed_error_to_response(exc, trace_id)


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions globally."""
    trace_id = getattr(request.state, "trace_id", "")
    logger.exception("Unhandled exception: {} trace_id={}", str(exc), trace_id)
    return error_response(
        INTERNAL_ERROR,
        "An unexpected error occurred. Please try again later.",
        trace_id,
    )


@app.get("/", response_model=SuccessResponse[dict])
def root():
    """API root endpoint."""
    return {
        "ok": True,
        "data": {
            "app": "Danah Abu Halifa",
            "version": "1.0.0",
            "status": "running",
            "dana": "ready",
            "docs": "/docs",
        },
    }


@app.get("/healthz", response_model=HealthStatus, tags=["health"])
def liveness_check():
    """Kubernetes liveness probe - checks if service is alive."""
    return HealthStatus(
        status="healthy",
        timestamp=datetime.now(timezone.utc).isoformat(),
        version="1.0.0",
        uptime_seconds=time.time() - _app_start_time,
    )


@app.get("/readyz", response_model=HealthStatus, tags=["health"])
def readiness_check(request: Request):
    """Kubernetes readiness probe - checks if service can accept traffic."""
    registry: ServiceRegistry = request.app.state.services
    service_health = registry.health_check()

    all_healthy = all(service_health.values())
    status = "healthy" if all_healthy else "degraded"

    return HealthStatus(
        status=status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        version="1.0.0",
        uptime_seconds=time.time() - _app_start_time,
    )


@app.get("/health", response_model=HealthStatus, tags=["health"])
def health():
    """Legacy health check endpoint."""
    return HealthStatus(
        status="healthy",
        timestamp=datetime.now(timezone.utc).isoformat(),
        version="1.0.0",
        uptime_seconds=time.time() - _app_start_time,
    )


@app.get("/v1/system/status", response_model=SuccessResponse[SystemStatus], tags=["system"])
def system_status():
    """Get current system status."""
    controller = MasterController()
    status_data = controller.get_system_status()

    return {
        "ok": True,
        "data": SystemStatus(**status_data),
    }
