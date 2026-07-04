"""Monitoring and metrics endpoints for observability."""

from __future__ import annotations

import platform
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from api.dependencies import get_service_registry
from core.service_registry import ServiceRegistry
from database.connection import DatabaseConnection

router = APIRouter(prefix="/v1/monitoring", tags=["monitoring"])

_app_start_time = time.time()


class MetricsResponse(BaseModel):
    """System metrics response."""

    uptime_seconds: float = Field(..., description="Application uptime in seconds")
    process_memory_mb: float | None = Field(None, description="Process memory usage in MB")
    python_version: str = Field(..., description="Python version")
    platform: str = Field(..., description="Platform information")
    timestamp: str = Field(..., description="Current UTC timestamp")


class ServiceMetrics(BaseModel):
    """Individual service metrics."""

    name: str = Field(..., description="Service name")
    healthy: bool = Field(..., description="Service health status")
    initialized: bool = Field(..., description="Whether service is initialized")


class DetailedMetrics(BaseModel):
    """Detailed system metrics."""

    system: MetricsResponse = Field(..., description="System-level metrics")
    services: list[ServiceMetrics] = Field(..., description="Service-level metrics")
    database: dict[str, int] | None = Field(None, description="Database pool statistics")


def get_process_memory() -> float | None:
    """Get current process memory usage in MB."""
    try:
        import psutil

        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024
    except ImportError:
        return None


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics():
    """Get basic system metrics for monitoring."""
    return MetricsResponse(
        uptime_seconds=time.time() - _app_start_time,
        process_memory_mb=get_process_memory(),
        python_version=platform.python_version(),
        platform=f"{platform.system()} {platform.release()}",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/metrics/detailed", response_model=DetailedMetrics)
async def get_detailed_metrics(
    registry: ServiceRegistry = Depends(get_service_registry),
):
    """Get detailed metrics including service health."""
    system_metrics = MetricsResponse(
        uptime_seconds=time.time() - _app_start_time,
        process_memory_mb=get_process_memory(),
        python_version=platform.python_version(),
        platform=f"{platform.system()} {platform.release()}",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    service_health = registry.health_check()
    service_metrics = [
        ServiceMetrics(
            name=name,
            healthy=healthy,
            initialized=True,
        )
        for name, healthy in service_health.items()
    ]

    # Try to get database metrics
    db_metrics = None
    db_conn = registry.get_optional("database")
    if db_conn and hasattr(db_conn, "get_pool_status"):
        try:
            db_metrics = db_conn.get_pool_status()
        except Exception:
            pass

    return DetailedMetrics(
        system=system_metrics,
        services=service_metrics,
        database=db_metrics,
    )


@router.get("/health/services")
async def service_health_check(
    registry: ServiceRegistry = Depends(get_service_registry),
):
    """Check health of all registered services."""
    health = registry.health_check()
    all_healthy = all(health.values())

    return {
        "ok": all_healthy,
        "status": "healthy" if all_healthy else "degraded",
        "services": health,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/info")
async def get_info():
    """Get application information."""
    return {
        "name": "Danah Abu Halifa",
        "version": "1.0.0",
        "description": "Smart Bed AI with Dana personality assistant",
        "api_version": "v1",
        "uptime_seconds": time.time() - _app_start_time,
    }
