"""Self-tests for RunContext and unique_title."""

import re

import pytest

from saas_testkit.context import RunContext, current_context, unique_title, using_context

_TRACEPARENT = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-01$")


def test_traceparent_matches_w3c_shape() -> None:
    ctx = RunContext.create(run_id="run", test_id="test_one")

    assert _TRACEPARENT.fullmatch(ctx.traceparent)
    assert ctx.headers() == {
        "X-Request-ID": "test_one",
        "traceparent": ctx.traceparent,
    }


def test_unique_title_embeds_run_and_test_ids() -> None:
    ctx = RunContext.create(run_id="run1", test_id="test1")

    with using_context(ctx):
        title = unique_title("task")

    assert title.startswith("task-run1-test1-")


def test_unique_title_changes_on_every_call() -> None:
    ctx = RunContext.create(run_id="run", test_id="node")

    with using_context(ctx):
        first = unique_title()
        second = unique_title()

    assert first != second
    assert first.startswith("task-run-node-")


def test_unique_title_without_context_raises() -> None:
    with pytest.raises(RuntimeError, match="RunContext is not bound"):
        unique_title("task")


def test_current_context_without_binding_raises() -> None:
    with pytest.raises(RuntimeError, match="RunContext is not bound"):
        current_context()
