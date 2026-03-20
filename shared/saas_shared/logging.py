import logging
from typing import Any

import structlog
from structlog.typing import EventDict


def _add_service_name(service_name: str):
    def processor(logger: Any, method: str, event_dict: EventDict) -> EventDict:
        event_dict["service"] = service_name
        return event_dict
    return processor


def _inject_dd_trace_context(
    logger: Any, method: str, event_dict: EventDict
) -> EventDict:
    """Add Datadog APM correlation fields to every structured log line.

    When ddtrace is active (ddtrace-run or ddtrace.auto), this processor
    reads the current span from the thread/async-task local tracer and injects
    the four fields that Datadog requires to link a log entry to its trace:

        dd.trace_id  – decimal string, used as the join key in the Datadog UI
        dd.span_id   – decimal string
        dd.service   – matches DD_SERVICE env var
        dd.env       – matches DD_ENV env var

    If ddtrace is not installed, or no active span exists (e.g. background
    beat tasks before the first HTTP request), the fields are silently omitted.
    The processor is always safe to include in the chain.
    """
    try:
        from ddtrace import tracer  # type: ignore[import-untyped]

        span = tracer.current_span()
        if span is not None:
            ctx = span.context
            event_dict["dd.trace_id"] = str(ctx.trace_id)
            event_dict["dd.span_id"] = str(span.span_id)
            # service / env come from the DD_SERVICE / DD_ENV env vars that
            # ddtrace reads at startup — propagate them for completeness.
            if span.service:
                event_dict["dd.service"] = span.service
            env_tag = span.get_tag("env")
            if env_tag:
                event_dict["dd.env"] = env_tag
    except Exception:  # noqa: BLE001
        # Never let observability code break the application.
        pass
    return event_dict


def setup_logging(log_level: str = "INFO", service_name: str = "") -> None:

    level = getattr(logging, log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(message)s",
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_service_name(service_name),
            _inject_dd_trace_context,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
    )
