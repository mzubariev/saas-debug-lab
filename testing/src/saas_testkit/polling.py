"""Wait until a probe succeeds. Callers await this; they do not sleep themselves."""

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import cast

type Probe[T] = Callable[[], T | Awaitable[T]]


class PollTimeout(AssertionError):
    """`eventually` did not see a successful probe before `timeout`."""


async def eventually[T](
    fn: Probe[T],
    *,
    timeout: float = 10,  # noqa: ASYNC109  # public name is `timeout` (arch-core-infra §6.6)
    interval: float = 0.2,
    message: str = "",
) -> T:
    """Retry `fn` until it returns a non-None value or `timeout` elapses.

    `AssertionError` and a `None` result are retried. Any other exception
    propagates on the attempt that raised it.
    """
    if timeout < 0:
        raise ValueError("timeout must be >= 0")
    if interval < 0:
        raise ValueError("interval must be >= 0")

    started = time.monotonic()
    deadline = started + timeout
    last_error: AssertionError | None = None
    while True:
        try:
            result = await _call(fn)
        except AssertionError as exc:
            last_error = exc
        else:
            if result is not None:
                return result
            last_error = AssertionError("probe returned None")

        now = time.monotonic()
        if now >= deadline:
            detail = message or "condition was not met"
            elapsed = now - started
            raise PollTimeout(f"{detail} after {elapsed:.2f}s") from last_error
        remaining = deadline - now
        await asyncio.sleep(min(interval, remaining))


async def _call[T](fn: Probe[T]) -> T:
    value = fn()
    if inspect.isawaitable(value):
        return cast(T, await value)
    return value
