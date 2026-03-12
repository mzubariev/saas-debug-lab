from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor


def setup_telemetry(app):

    trace.set_tracer_provider(TracerProvider())

    FastAPIInstrumentor.instrument_app(app)