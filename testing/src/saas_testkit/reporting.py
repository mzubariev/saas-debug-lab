"""Jaeger link in the failure report when ``TRACING=1``."""

import os
from collections.abc import Iterator
from typing import cast

import pytest

TRACE_ID = pytest.StashKey[str]()
_TRACE_URL = "http://localhost:16687/trace/"


def remember_trace_id(item: pytest.Item, trace_id: str) -> None:
    item.stash[TRACE_ID] = trace_id


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Iterator[None]:
    outcome = yield  # pyright: ignore[reportUnknownVariableType]
    if os.environ.get("TRACING") != "1":
        return
    getter = getattr(cast(object, outcome), "get_result", None)
    if not callable(getter):
        return
    report = cast(pytest.TestReport, getter())
    if report.when not in {"setup", "call"} or not report.failed:
        return
    trace_id = item.stash.get(TRACE_ID, "")
    if trace_id:
        report.sections.append(("Jaeger", f"{_TRACE_URL}{trace_id}"))
