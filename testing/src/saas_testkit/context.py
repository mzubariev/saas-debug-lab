"""Per-run and per-test identity, plus the headers a test's HTTP calls carry."""

import secrets
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True, slots=True, kw_only=True)
class RunContext:
    """Identifies one pytest session (`run_id`) and one test (`test_id`)."""

    run_id: str
    test_id: str
    trace_id: str
    span_id: str

    @classmethod
    def create(cls, *, run_id: str, test_id: str) -> RunContext:
        return cls(
            run_id=run_id,
            test_id=test_id,
            trace_id=uuid4().hex,
            span_id=secrets.token_hex(8),
        )

    @property
    def traceparent(self) -> str:
        """W3C `traceparent` for this test (`00-{trace_id}-{span_id}-01`)."""
        return f"00-{self.trace_id}-{self.span_id}-01"

    def headers(self) -> dict[str, str]:
        return {"X-Request-ID": self.test_id, "traceparent": self.traceparent}


_current: ContextVar[RunContext | None] = ContextVar("saas_testkit_run_context", default=None)


def bind_context(ctx: RunContext) -> Token[RunContext | None]:
    return _current.set(ctx)


def reset_context(token: Token[RunContext | None]) -> None:
    _current.reset(token)


def current_context() -> RunContext:
    ctx = _current.get()
    if ctx is None:
        raise RuntimeError("RunContext is not bound; a test fixture must bind it first")
    return ctx


@contextmanager
def using_context(ctx: RunContext) -> Generator[RunContext]:
    token = bind_context(ctx)
    try:
        yield ctx
    finally:
        reset_context(token)


def unique_title(prefix: str = "task") -> str:
    """A title unique to this test and this call. Requires a bound `RunContext`."""
    ctx = current_context()
    return f"{prefix}-{ctx.run_id}-{ctx.test_id}-{uuid4().hex[:8]}"
