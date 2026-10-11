"""Self-tests for RunContext and unique_title."""

import hashlib
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


def test_unique_title_is_short_and_omits_the_nodeid() -> None:
    run_id = "abcdef1234567890"
    test_id = (
        "tests/e2e_ui/task_lifecycle/test_board.py::"
        "test_created_task_stays_in_each_column_after_reload"
    )
    ctx = RunContext.create(run_id=run_id, test_id=test_id)
    digest = hashlib.sha256(test_id.encode()).hexdigest()[:6]

    with using_context(ctx):
        title = unique_title("task")

    assert re.fullmatch(rf"task-{run_id[:6]}-{digest}-[0-9a-f]{{6}}", title)
    assert len(title) == 25
    assert test_id not in title
    assert ctx.headers()["X-Request-ID"] == test_id


def test_unique_title_changes_on_every_call() -> None:
    ctx = RunContext.create(run_id="aabbccddeeff", test_id="node::id")
    digest = hashlib.sha256(b"node::id").hexdigest()[:6]
    stem = f"task-aabbcc-{digest}-"

    with using_context(ctx):
        first = unique_title()
        second = unique_title()

    assert first != second
    assert first.startswith(stem)
    assert second.startswith(stem)
    assert len(first) == len(stem) + 6


def test_unique_title_without_context_raises() -> None:
    with pytest.raises(RuntimeError, match="RunContext is not bound"):
        unique_title("task")


def test_current_context_without_binding_raises() -> None:
    with pytest.raises(RuntimeError, match="RunContext is not bound"):
        current_context()
