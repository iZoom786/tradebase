"""
Observability setup - logging, tracing, metrics
"""

import logging
import structlog
from typing import Optional
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from prometheus_client import Counter, Histogram, Gauge, start_http_server


# Prometheus Metrics
message_counter = Counter(
    'messages_total',
    'Total messages processed',
    ['service', 'status']
)

processing_duration = Histogram(
    'processing_duration_seconds',
    'Processing duration',
    ['service', 'operation']
)

active_positions = Gauge(
    'active_positions',
    'Number of active trading positions',
    ['symbol']
)

model_accuracy = Gauge(
    'model_accuracy',
    'Model prediction accuracy',
    ['model_type', 'symbol']
)


def setup_logging():
    """Configure structured logging with structlog"""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def setup_tracing(
    service_name: str,
    jaeger_endpoint: Optional[str] = None
) -> trace.Tracer:
    """
    Setup OpenTelemetry tracing

    Args:
        service_name: Name of the service
        jaeger_endpoint: Jaeger collector endpoint

    Returns:
        Configured tracer
    """
    resource = Resource(attributes={
        SERVICE_NAME: service_name
    })

    provider = TracerProvider(resource=resource)

    if jaeger_endpoint:
        jaeger_exporter = JaegerExporter(
            agent_host_name=jaeger_endpoint.split(":")[1].strip("//"),
            agent_port=int(jaeger_endpoint.split(":")[-1].rstrip("/"))
        )
        provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))

    trace.set_tracer_provider(provider)
    return trace.get_tracer(__name__)


def setup_metrics(port: int = 9091):
    """
    Start Prometheus metrics server

    Args:
        port: Port to expose metrics on
    """
    start_http_server(port)
