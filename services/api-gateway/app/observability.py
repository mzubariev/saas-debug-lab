from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor


def setup_telemetry(app):

    FastAPIInstrumentor.instrument_app(app)