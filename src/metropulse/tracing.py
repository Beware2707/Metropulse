"""Optional OpenTelemetry tracing.

Tracing activates only when BOTH are true:
  1. ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set in the environment, and
  2. the optional dependencies are installed (``pip install metropulse[tracing]``).

Otherwise every call is a logged no-op — the core service carries zero
telemetry dependencies and zero overhead by default.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def configure_tracing(service_name: str) -> bool:
    """Initialise the OTLP tracer provider if configured and installed.

    Returns True when tracing is active.
    """
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        logger.debug("tracing disabled: OTEL_EXPORTER_OTLP_ENDPOINT not set")
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning(
            "OTEL_EXPORTER_OTLP_ENDPOINT is set but opentelemetry is not "
            "installed; run: pip install 'metropulse[tracing]'"
        )
        return False
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    logger.info("tracing enabled for %s -> %s", service_name, endpoint)
    return True


def instrument_app(app: Any) -> bool:
    """Attach FastAPI auto-instrumentation when the package is available.

    Returns True when the app was instrumented.
    """
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except ImportError:
        logger.warning(
            "FastAPI instrumentation not installed; HTTP spans are unavailable"
        )
        return False
    FastAPIInstrumentor.instrument_app(app)
    return True
