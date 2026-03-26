from opentelemetry import trace
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


def setup_telemetry(app, service_name: str, otlp_endpoint: str) -> None:
    # So browser ``traceparent`` (W3C Trace Context) becomes the active OTEL span → logs get ``trace_id``.
    set_global_textmap(
        CompositePropagator(
            [
                TraceContextTextMapPropagator(),
                W3CBaggagePropagator(),
            ]
        )
    )

    resource = Resource.create({SERVICE_NAME: service_name})

    exporter = OTLPSpanExporter(endpoint=otlp_endpoint)

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
