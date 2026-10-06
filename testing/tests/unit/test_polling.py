"""Self-tests for eventually. Intervals stay tiny so the suite needs no Docker."""

import pytest

from saas_testkit.polling import PollTimeout, eventually


async def test_eventually_returns_first_non_none_value() -> None:
    calls = 0

    def probe() -> str | None:
        nonlocal calls
        calls += 1
        if calls < 3:
            return None
        return "ready"

    assert await eventually(probe, timeout=1, interval=0.01) == "ready"
    assert calls == 3


async def test_eventually_retries_assertion_errors() -> None:
    calls = 0

    def probe() -> int:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise AssertionError("not yet")
        return 0

    assert await eventually(probe, timeout=1, interval=0.01) == 0


async def test_eventually_awaits_async_probes() -> None:
    async def probe() -> str:
        return "ok"

    assert await eventually(probe, timeout=1, interval=0.01) == "ok"


async def test_eventually_propagates_unexpected_errors() -> None:
    def probe() -> str:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await eventually(probe, timeout=1, interval=0.01)


async def test_eventually_timeout_reports_message_and_elapsed() -> None:
    def probe() -> None:
        raise AssertionError("still empty")

    with pytest.raises(PollTimeout, match=r"still waiting after 0\.\d+s") as raised:
        await eventually(probe, timeout=0.05, interval=0.01, message="still waiting")

    assert isinstance(raised.value.__cause__, AssertionError)


async def test_eventually_rejects_negative_timeout() -> None:
    with pytest.raises(ValueError, match="timeout"):
        await eventually(lambda: "x", timeout=-1, interval=0.01)


async def test_eventually_accepts_false() -> None:
    assert await eventually(lambda: False, timeout=1, interval=0.01) is False
