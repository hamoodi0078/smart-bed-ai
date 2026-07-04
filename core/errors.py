from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from fastapi.responses import JSONResponse

# ── Error codes ─────────────────────────────────────────────────────
DEVICE_OFFLINE: Final[str] = "DEVICE_OFFLINE"
UNAUTHORIZED: Final[str] = "UNAUTHORIZED"
FORBIDDEN: Final[str] = "FORBIDDEN"
RATE_LIMITED: Final[str] = "RATE_LIMITED"
VALIDATION_ERROR: Final[str] = "VALIDATION_ERROR"
NOT_FOUND: Final[str] = "NOT_FOUND"
INVALID_SCENE_CONFIG: Final[str] = "INVALID_SCENE_CONFIG"
TRIAL_ALREADY_USED: Final[str] = "TRIAL_ALREADY_USED"
NOTHING_TO_UNDO: Final[str] = "NOTHING_TO_UNDO"
SUBSCRIPTION_REQUIRED: Final[str] = "SUBSCRIPTION_REQUIRED"
DEVICE_BUSY: Final[str] = "DEVICE_BUSY"
TIMEOUT: Final[str] = "TIMEOUT"
INTERNAL_ERROR: Final[str] = "INTERNAL_ERROR"

_STATUS_BY_CODE: Final[dict[str, int]] = {
    DEVICE_OFFLINE: 503,
    UNAUTHORIZED: 401,
    FORBIDDEN: 403,
    RATE_LIMITED: 429,
    VALIDATION_ERROR: 422,
    NOT_FOUND: 404,
    INVALID_SCENE_CONFIG: 422,
    TRIAL_ALREADY_USED: 409,
    NOTHING_TO_UNDO: 404,
    SUBSCRIPTION_REQUIRED: 402,
    DEVICE_BUSY: 409,
    TIMEOUT: 504,
    INTERNAL_ERROR: 500,
}


# ── Base exception hierarchy ────────────────────────────────────────
class BedError(Exception):
    """Base exception for all Smart Bed application errors."""

    def __init__(self, message: str = "An unexpected error occurred"):
        super().__init__(message)
        self.message = message


class DeviceOfflineError(BedError):
    """Raised when a device is unreachable."""

    def __init__(self, device_id: str = ""):
        msg = f"Device {device_id} is offline" if device_id else "Device is offline"
        super().__init__(msg)
        self.device_id = device_id


class AuthorizationError(BedError):
    """Raised for authentication / authorization failures."""

    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message)


class SubscriptionRequiredError(BedError):
    """Raised when a premium feature is accessed without subscription."""

    def __init__(self, feature: str = ""):
        msg = f"Subscription required for: {feature}" if feature else "Active subscription required"
        super().__init__(msg)
        self.feature = feature


class VoiceProcessingError(BedError):
    """Raised when voice pipeline (STT/TTS/LLM) encounters an error."""

    def __init__(self, stage: str = "", detail: str = ""):
        msg = (
            f"Voice processing failed at {stage}: {detail}"
            if stage
            else detail or "Voice processing error"
        )
        super().__init__(msg)
        self.stage = stage
        self.detail = detail


class ConfigurationError(BedError):
    """Raised for invalid or missing configuration."""

    def __init__(self, key: str = "", message: str = ""):
        msg = (
            f"Configuration error for '{key}': {message}"
            if key
            else message or "Configuration error"
        )
        super().__init__(msg)
        self.key = key


# ── API-level error (legacy compat) ────────────────────────────────
class APIError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        retry_after: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retry_after = retry_after


# ── Helpers ─────────────────────────────────────────────────────────
def error_response(
    code: str, message: str, trace_id: str, retry_after: int | None = None
) -> JSONResponse:
    normalized_code = str(code or INTERNAL_ERROR).strip() or INTERNAL_ERROR
    status_code = _STATUS_BY_CODE.get(normalized_code, 500)
    retry_value = int(retry_after) if retry_after is not None else None
    trace_value = str(trace_id or "")
    response = JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "error": {
                "code": normalized_code,
                "message": str(message or "Request failed"),
                "trace_id": trace_value,
                "retry_after": retry_value,
            },
        },
        headers={"X-Trace-Id": trace_value},
    )
    if retry_value is not None:
        response.headers["Retry-After"] = str(retry_value)
    return response


def bed_error_to_response(exc: BedError, trace_id: str = "") -> JSONResponse:
    """Convert a BedError to a standardized API response."""
    if isinstance(exc, DeviceOfflineError):
        return error_response(DEVICE_OFFLINE, exc.message, trace_id)
    if isinstance(exc, AuthorizationError):
        return error_response(UNAUTHORIZED, exc.message, trace_id)
    if isinstance(exc, SubscriptionRequiredError):
        return error_response(SUBSCRIPTION_REQUIRED, exc.message, trace_id)
    if isinstance(exc, VoiceProcessingError):
        return error_response(INTERNAL_ERROR, exc.message, trace_id)
    if isinstance(exc, ConfigurationError):
        return error_response(INTERNAL_ERROR, exc.message, trace_id)
    return error_response(INTERNAL_ERROR, exc.message, trace_id)
