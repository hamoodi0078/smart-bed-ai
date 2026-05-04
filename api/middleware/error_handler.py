"""Global error handling middleware for FastAPI."""

from __future__ import annotations

import logging
from typing import Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.errors import (
    APIError,
    BedError,
    bed_error_to_response,
    error_response,
    INTERNAL_ERROR,
    VALIDATION_ERROR,
)

logger = logging.getLogger("api.error_handler")


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Catches and formats all unhandled exceptions."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            response = await call_next(request)
            return response
        except BedError as exc:
            trace_id = getattr(request.state, "trace_id", "")
            logger.warning(
                "BedError caught: %s",
                exc.message,
                extra={"trace_id": trace_id, "error_type": type(exc).__name__},
            )
            return bed_error_to_response(exc, trace_id)
        except APIError as exc:
            trace_id = getattr(request.state, "trace_id", "")
            logger.warning(
                "APIError caught: %s",
                exc.message,
                extra={"trace_id": trace_id, "error_code": exc.code},
            )
            return error_response(exc.code, exc.message, trace_id, exc.retry_after)
        except ValueError as exc:
            trace_id = getattr(request.state, "trace_id", "")
            logger.warning(
                "ValueError caught: %s",
                str(exc),
                extra={"trace_id": trace_id},
            )
            return error_response(VALIDATION_ERROR, str(exc), trace_id)
        except Exception as exc:
            trace_id = getattr(request.state, "trace_id", "")
            logger.exception(
                "Unhandled exception: %s",
                str(exc),
                extra={"trace_id": trace_id},
            )
            return error_response(
                INTERNAL_ERROR,
                "An unexpected error occurred. Please try again later.",
                trace_id,
            )
