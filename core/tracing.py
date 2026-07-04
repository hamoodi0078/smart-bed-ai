"""OpenTelemetry tracing setup for the Danah Smart Bed API.

Initialises a TracerProvider with an OTLP exporter (or console fallback),
wires FastAPI auto-instrumentation, and exposes a helper to get a tracer.

Environment variables:
    OTEL_EXPORTER_OTLP_ENDPOINT  — gRPC endpoint, e.g. http://localhost:4317
    OTEL_SERVICE_NAME            — override the default service name
    OTEL_TRACES_EXPORTER         — 'otlp' (default) | 'console' | 'none'
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from fastapi import FastAPI

_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "danah-smart-bed")
_EXPORTER = os.getenv("OTEL_TRACES_EXPORTER", "otlp").lower()
_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

_tracer_provider = None


def setup_tracing(app: "FastAPI | None" = None) -> None:
    """Initialise OpenTelemetry tracing and optionally instrument a FastAPI app.

    Call once at application startup (inside the lifespan handler or at module level).
    """
    global _tracer_provider

    if _EXPORTER == "none":
        logger.info("OpenTelemetry tracing disabled (OTEL_TRACES_EXPORTER=none)")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": _SERVICE_NAME})
        provider = TracerProvider(resource=resource)

        if _EXPORTER == "console":
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter

            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            logger.info("OpenTelemetry tracing: console exporter")
        else:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

                exporter = OTLPSpanExporter(endpoint=_OTLP_ENDPOINT, insecure=True)
                provider.add_span_processor(BatchSpanProcessor(exporter))
                logger.info("OpenTelemetry tracing: OTLP exporter → {}", _OTLP_ENDPOINT)
            except ImportError:
                from opentelemetry.sdk.trace.export import ConsoleSpanExporter

                provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
                logger.warning(
                    "opentelemetry-exporter-otlp-proto-grpc not installed; "
                    "falling back to console exporter"
                )

        trace.set_tracer_provider(provider)
        _tracer_provider = provider

        if app is not None:
            _instrument_fastapi(app)

        logger.info("OpenTelemetry tracing initialised (service={})", _SERVICE_NAME)

    except Exception as exc:
        logger.warning("OpenTelemetry setup failed — tracing disabled: {}", exc)


def _instrument_fastapi(app: "FastAPI") -> None:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls="/healthz,/metrics,/docs,/openapi.json,/redoc",
        )
        logger.debug("FastAPI auto-instrumented with OpenTelemetry")
    except Exception as exc:
        logger.warning("FastAPI OpenTelemetry instrumentation failed: {}", exc)


def get_tracer(name: str = _SERVICE_NAME):
    """Return a tracer for manual span creation."""
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except Exception:
        return _NoOpTracer()


class _NoOpTracer:
    """Fallback tracer when OpenTelemetry is unavailable."""

    def start_as_current_span(self, name: str, **_):
        from contextlib import contextmanager

        @contextmanager
        def _noop():
            yield None

        return _noop()

    def start_span(self, name: str, **_):
        return _NoOpSpan()


class _NoOpSpan:
    def set_attribute(self, *_):
        pass

    def set_status(self, *_):
        pass

    def record_exception(self, *_):
        pass

    def end(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass
