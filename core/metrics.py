"""Shared Prometheus metrics — single registration point.

Both ``api/app_factory.py`` and ``web_server.py`` import from here instead
of creating their own Counter / Histogram instances.  This prevents the
``ValueError: Duplicated timeseries`` that occurs when both apps are loaded
in the same process (which happens when app_factory mounts web_server).
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "danah_http_requests_total",
    "Total HTTP requests handled by the Danah Smart Bed API",
    ["method", "path", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "danah_http_request_latency_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
)

ERROR_COUNT = Counter(
    "danah_http_errors_total",
    "Total HTTP error responses",
    ["method", "path", "status_code"],
)
