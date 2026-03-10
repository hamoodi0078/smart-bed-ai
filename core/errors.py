from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from fastapi.responses import JSONResponse

DEVICE_OFFLINE: Final[str] = "DEVICE_OFFLINE"
UNAUTHORIZED: Final[str] = "UNAUTHORIZED"
RATE_LIMITED: Final[str] = "RATE_LIMITED"
VALIDATION_ERROR: Final[str] = "VALIDATION_ERROR"
INTERNAL_ERROR: Final[str] = "INTERNAL_ERROR"

_STATUS_BY_CODE: Final[dict[str, int]] = {
    DEVICE_OFFLINE: 503,
    UNAUTHORIZED: 401,
    RATE_LIMITED: 429,
    VALIDATION_ERROR: 422,
    INTERNAL_ERROR: 500,
}


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


def error_response(code: str, message: str, trace_id: str, retry_after: int | None = None) -> JSONResponse:
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
