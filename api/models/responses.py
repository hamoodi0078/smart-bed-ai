"""Standardized API response models for type safety and documentation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class ErrorDetail(BaseModel):
    """Error detail structure."""

    code: str = Field(..., description="Error code identifier")
    message: str = Field(..., description="Human-readable error message")
    trace_id: str | None = Field(None, description="Request trace ID for debugging")
    retry_after: int | None = Field(None, description="Seconds to wait before retry")


class ErrorResponse(BaseModel):
    """Standard error response envelope."""

    ok: bool = Field(False, description="Always false for errors")
    error: ErrorDetail = Field(..., description="Error details")


class SuccessResponse(BaseModel, Generic[T]):
    """Standard success response envelope."""

    ok: bool = Field(True, description="Always true for success")
    data: T = Field(..., description="Response payload")
    meta: dict[str, Any] | None = Field(None, description="Optional metadata")


class HealthStatus(BaseModel):
    """Health check status."""

    status: str = Field(..., description="Overall health status: healthy, degraded, unhealthy")
    timestamp: str = Field(..., description="ISO timestamp of health check")
    version: str = Field(..., description="Application version")
    uptime_seconds: float | None = Field(None, description="Service uptime in seconds")


class ServiceHealth(BaseModel):
    """Individual service health status."""

    name: str = Field(..., description="Service name")
    healthy: bool = Field(..., description="Whether service is healthy")
    latency_ms: float | None = Field(None, description="Service response latency")
    error: str | None = Field(None, description="Error message if unhealthy")


class DetailedHealthResponse(BaseModel):
    """Detailed health check with service breakdown."""

    status: str = Field(..., description="Overall health status")
    timestamp: str = Field(..., description="ISO timestamp")
    version: str = Field(..., description="Application version")
    services: list[ServiceHealth] = Field(default_factory=list, description="Individual service health")
    uptime_seconds: float | None = Field(None, description="Service uptime")


class SystemStatus(BaseModel):
    """System status information."""

    dana_personality: str = Field(..., description="Current Dana personality mode")
    islamic_mode: bool = Field(..., description="Whether Islamic mode is enabled")
    spotify_connected: bool = Field(..., description="Whether Spotify is connected")
    guest_mode_active: bool = Field(..., description="Whether guest mode is active")
    user_name: str = Field(..., description="Current user name")


class BackupResult(BaseModel):
    """Backup operation result."""

    backup_id: str = Field(..., description="Unique backup identifier")
    backup_type: str = Field(..., description="Type of backup performed")
    path: str = Field(..., description="Backup file path")
    size_bytes: int = Field(..., description="Backup file size")
    created_at: str = Field(..., description="ISO timestamp of backup creation")
    success: bool = Field(..., description="Whether backup succeeded")


class PaginationMeta(BaseModel):
    """Pagination metadata."""

    page: int = Field(1, ge=1, description="Current page number")
    per_page: int = Field(20, ge=1, le=100, description="Items per page")
    total: int = Field(0, ge=0, description="Total number of items")
    total_pages: int = Field(0, ge=0, description="Total number of pages")


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response with metadata."""

    ok: bool = Field(True, description="Success indicator")
    data: list[T] = Field(..., description="Page of items")
    pagination: PaginationMeta = Field(..., description="Pagination metadata")
