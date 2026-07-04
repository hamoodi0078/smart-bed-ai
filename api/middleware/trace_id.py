"""Request tracing middleware for distributed request tracking."""

from __future__ import annotations

import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class TraceIDMiddleware(BaseHTTPMiddleware):
    """Adds a unique trace ID to each request for debugging and monitoring."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        trace_id = request.headers.get("X-Trace-ID") or request.headers.get("X-Request-ID")

        if not trace_id:
            trace_id = str(uuid.uuid4())

        request.state.trace_id = trace_id

        response = await call_next(request)

        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Request-ID"] = trace_id

        return response
