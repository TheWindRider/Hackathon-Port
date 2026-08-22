"""OpenTelemetry instrumentation for the Agentic Software Factory.

This module initializes tracing and provides helpers for adding manual spans,
recording failures, and tracking factory pipeline steps.
"""

import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode


def init_telemetry(service_name: str = "hackathon-factory", service_version: str = "0.1.0") -> None:
    """Initialize OpenTelemetry tracing with OTLP/gRPC exporter for SigNoz.

    Uses environment variables:
        OTEL_EXPORTER_OTLP_ENDPOINT: SigNoz ingestion endpoint
        OTEL_EXPORTER_OTLP_HEADERS: optional explicit headers string
        SIGNOZ_INGESTION_KEY: used to build signoz-ingestion-key header if OTEL_EXPORTER_OTLP_HEADERS is not set
    """
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
        "deployment.environment": os.getenv("DEPLOYMENT_ENVIRONMENT", "dev"),
    })

    provider = TracerProvider(resource=resource)

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    headers = _build_headers()
    exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers)

    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)

    trace.set_tracer_provider(provider)


def _build_headers() -> dict[str, str]:
    """Build OTLP headers from explicit env var or SIGNOZ_INGESTION_KEY."""
    explicit_headers = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "").strip()
    if explicit_headers:
        return _parse_headers(explicit_headers)

    ingestion_key = os.getenv("SIGNOZ_INGESTION_KEY", "").strip()
    if ingestion_key:
        return {"signoz-ingestion-key": ingestion_key}

    return {}


def _parse_headers(headers_str: str) -> dict[str, str]:
    """Parse OTLP headers string into a dictionary."""
    headers: dict[str, str] = {}
    if not headers_str:
        return headers
    for item in headers_str.split(","):
        key, _, value = item.strip().partition("=")
        if key and value:
            headers[key.strip()] = value.strip()
    return headers


@contextmanager
def factory_step(step_name: str, **attributes: Any) -> Generator[trace.Span, None, None]:
    """Context manager for tracing a factory pipeline step.

    Usage:
        with factory_step("parse-brief", brief_id="123") as span:
            ...
    """
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(step_name) as span:
        for key, value in attributes.items():
            span.set_attribute(f"factory.{key}", value)
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


def set_span_attributes(**attributes: Any) -> None:
    """Set attributes on the current active span."""
    span = trace.get_current_span()
    for key, value in attributes.items():
        span.set_attribute(key, value)


def add_event(event_name: str, attributes: dict[str, Any] | None = None) -> None:
    """Add an event to the current active span."""
    span = trace.get_current_span()
    span.add_event(event_name, attributes or {})
