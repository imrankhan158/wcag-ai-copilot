from __future__ import annotations

import logging
import os
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

logger = logging.getLogger("wcag_common.observability.tracing")


def setup_opentelemetry(app, service_name: str) -> None:
    """Initializes OpenTelemetry SDK and instruments the FastAPI application."""
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    
    if not endpoint:
        logger.info("OTEL_EXPORTER_OTLP_ENDPOINT not set. OpenTelemetry tracing is disabled.")
        return

    logger.info(f"Initializing OpenTelemetry tracing targeting: {endpoint}")
    try:
        resource = Resource.attributes({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        
        # OTLP gRPC span exporter
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)
        
        trace.set_tracer_provider(provider)
        
        # Auto-instrument FastAPI routes
        FastAPIInstrumentor.instrument_app(app)
        logger.info("OpenTelemetry tracing initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize OpenTelemetry: {e}")
        # Proceed without crashing downstream services
