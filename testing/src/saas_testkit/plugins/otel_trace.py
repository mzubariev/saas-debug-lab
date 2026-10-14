"""Export this pytest run to Jaeger when ``TRACING=1``.

``pytest-opentelemetry`` propagates a parent across xdist, but its entry point
loads on every run and it adds fixture spans. This plugin stays inactive unless
``TRACING=1``.
"""

import os
import warnings
from collections.abc import Iterator
from typing import cast

import pytest
from xdist.workermanage import WorkerController  # pyright: ignore[reportMissingTypeStubs]

from saas_testkit.reporting import remember_trace_id

_ENDPOINT = os.environ.get("TRACING_ENDPOINT", "").strip() or "http://127.0.0.1:4319"
_SERVICE = "saas-testkit"
_CALL_REPORT = pytest.StashKey[pytest.TestReport]()


def _enabled() -> bool:
    return os.environ.get("TRACING") == "1"


def current_traceparent() -> str | None:
    """W3C header for the active span, or ``None`` when tracing is off or idle."""
    if not _enabled():
        return None
    try:
        from opentelemetry import trace
    except Exception as exc:
        warnings.warn(f"tracing traceparent unavailable: {exc}", RuntimeWarning, stacklevel=2)
        return None
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None
    return f"00-{ctx.trace_id:032x}-{ctx.span_id:016x}-{int(ctx.trace_flags):02x}"


def pytest_configure(config: pytest.Config) -> None:
    if not _enabled():
        return
    try:
        _boot(config)
    except Exception as exc:
        warnings.warn(f"tracing setup failed: {exc}", RuntimeWarning, stacklevel=2)


def pytest_configure_node(node: WorkerController) -> None:
    if not _enabled():
        return
    parent = getattr(node.config, "_otel_traceparent", None)
    if isinstance(parent, str) and parent:
        cast(dict[str, object], getattr(node, "workerinput", {}))["traceparent"] = parent


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item: pytest.Item) -> Iterator[None]:
    if not _enabled() or getattr(item.config, "_otel_ready", False) is not True:
        yield
        return
    started = _open_span(item)
    try:
        yield
    finally:
        _close_span(item, started)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Iterator[None]:
    outcome = yield  # pyright: ignore[reportUnknownVariableType]
    if not _enabled():
        return
    getter = getattr(cast(object, outcome), "get_result", None)
    if not callable(getter):
        return
    report = cast(pytest.TestReport, getter())
    if report.when == "call":
        item.stash[_CALL_REPORT] = report


def pytest_sessionfinish(session: pytest.Session) -> None:
    if not _enabled():
        return
    _flush(session.config)


def _boot(config: pytest.Config) -> None:
    from collections.abc import Sequence

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
    from opentelemetry.sdk.trace.sampling import ALWAYS_ON

    class _QuietExporter(SpanExporter):
        def __init__(self, inner: SpanExporter) -> None:
            self._inner = inner

        def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
            try:
                return self._inner.export(spans)
            except Exception as exc:
                warnings.warn(f"otlp export failed: {exc}", RuntimeWarning, stacklevel=2)
                return SpanExportResult.FAILURE

        def shutdown(self) -> None:
            try:
                self._inner.shutdown()
            except Exception as exc:
                warnings.warn(f"otlp shutdown failed: {exc}", RuntimeWarning, stacklevel=2)

        def force_flush(self, timeout_millis: int = 30000) -> bool:
            try:
                return self._inner.force_flush(timeout_millis)
            except Exception as exc:
                warnings.warn(f"otlp force_flush failed: {exc}", RuntimeWarning, stacklevel=2)
                return False

    provider = TracerProvider(
        resource=Resource.create({SERVICE_NAME: _SERVICE}),
        sampler=ALWAYS_ON,
    )
    provider.add_span_processor(
        BatchSpanProcessor(_QuietExporter(OTLPSpanExporter(endpoint=_ENDPOINT)))
    )
    trace.set_tracer_provider(provider)
    config._otel_provider = provider  # type: ignore[attr-defined]
    if hasattr(config, "workerinput"):
        parent = _worker_traceparent(config)
        if parent is not None:
            config._otel_traceparent = parent  # type: ignore[attr-defined]
    else:
        span = trace.get_tracer(_SERVICE).start_span("pytest")
        config._otel_root = span  # type: ignore[attr-defined]
        config._otel_traceparent = _format_span(span)  # type: ignore[attr-defined]
    config._otel_ready = True  # type: ignore[attr-defined]


def _worker_traceparent(config: pytest.Config) -> str | None:
    raw = getattr(config, "workerinput", None)
    if not isinstance(raw, dict):
        return None
    value = cast(dict[str, object], raw).get("traceparent")
    if isinstance(value, str) and value:
        return value
    return None


def _format_span(span: object) -> str:
    from opentelemetry import trace

    if not isinstance(span, trace.Span):
        raise RuntimeError("root span is missing")
    ctx = span.get_span_context()
    return f"00-{ctx.trace_id:032x}-{ctx.span_id:016x}-{int(ctx.trace_flags):02x}"


def _parent_context(config: pytest.Config) -> object:
    from opentelemetry import context as otel_context
    from opentelemetry import trace
    from opentelemetry.propagate import extract

    root = getattr(config, "_otel_root", None)
    if isinstance(root, trace.Span):
        return trace.set_span_in_context(root)
    raw = getattr(config, "_otel_traceparent", None)
    if isinstance(raw, str) and raw:
        return extract({"traceparent": raw})
    return otel_context.Context()


def _open_span(item: pytest.Item) -> tuple[object, object] | None:
    try:
        from opentelemetry import context as otel_context
        from opentelemetry import trace

        parent = cast(otel_context.Context, _parent_context(item.config))
        span = trace.get_tracer(_SERVICE).start_span(item.nodeid, context=parent)
        token = otel_context.attach(trace.set_span_in_context(span))
        ctx = span.get_span_context()
        if ctx.is_valid:
            remember_trace_id(item, f"{ctx.trace_id:032x}")
    except Exception as exc:
        warnings.warn(f"tracing span skipped: {exc}", RuntimeWarning, stacklevel=2)
        return None
    return span, token


def _close_span(item: pytest.Item, started: tuple[object, object] | None) -> None:
    if started is None:
        return
    span, token = started
    try:
        from opentelemetry import context as otel_context
        from opentelemetry.trace import Status, StatusCode

        report = item.stash.get(_CALL_REPORT, None)
        if isinstance(report, pytest.TestReport):
            outcome_name = _test_outcome(report)
            set_attribute = getattr(span, "set_attribute", None)
            if callable(set_attribute):
                set_attribute("test.outcome", outcome_name)
            if outcome_name == "failed":
                set_status = getattr(span, "set_status", None)
                if callable(set_status):
                    set_status(Status(StatusCode.ERROR, outcome_name))
        otel_context.detach(token)  # pyright: ignore[reportArgumentType]
        end = getattr(span, "end", None)
        if callable(end):
            end()
    except Exception as exc:
        warnings.warn(f"tracing span close failed: {exc}", RuntimeWarning, stacklevel=2)


def _test_outcome(report: pytest.TestReport) -> str:
    wasxfail = getattr(report, "wasxfail", None)
    if report.outcome == "skipped" or (wasxfail and not report.failed):
        return "skipped"
    if report.failed:
        return "failed"
    return "passed"


def _flush(config: pytest.Config) -> None:
    root = getattr(config, "_otel_root", None)
    if root is not None:
        try:
            end = getattr(root, "end", None)
            if callable(end):
                end()
        except Exception as exc:
            warnings.warn(f"tracing root span failed: {exc}", RuntimeWarning, stacklevel=2)
    provider = getattr(config, "_otel_provider", None)
    flush = getattr(provider, "force_flush", None)
    if not callable(flush):
        return
    try:
        flush()
    except Exception as exc:
        warnings.warn(f"otlp force_flush failed: {exc}", RuntimeWarning, stacklevel=2)
