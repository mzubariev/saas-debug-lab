"""One Redpanda consumer per worker. Subscribe before tests produce."""

import json
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from typing import cast

from aiokafka import AIOKafkaConsumer  # pyright: ignore[reportMissingTypeStubs]

from saas_testkit.domain.events import Envelope
from saas_testkit.polling import PollTimeout


class KafkaEventReader:
    """Reads real Kafka records and returns the ones `match` accepts.

    Records for other topics, and records `match` rejects, stay buffered so a
    later `wait_for` can still see them.
    """

    def __init__(self, bootstrap_servers: str, *, group_id: str) -> None:
        if not group_id:
            raise ValueError("group_id is required")
        self._bootstrap = bootstrap_servers
        self._group_id = group_id
        self._consumer: object | None = None
        self._pending: dict[str, list[Envelope]] = defaultdict(list)

    async def start(self, *topics: str) -> None:
        """Join `group_id` and subscribe. `start` returns after assignment."""
        if not topics:
            raise ValueError("subscribe to at least one topic")
        if self._consumer is not None:
            raise RuntimeError("KafkaEventReader is already started")
        consumer = _open_consumer(self._bootstrap, self._group_id, topics)
        await _call(consumer, "start")
        self._consumer = consumer

    async def stop(self) -> None:
        consumer = self._consumer
        self._consumer = None
        if consumer is not None:
            await _call(consumer, "stop")

    async def wait_for(
        self,
        topic: str,
        *,
        match: Callable[[Envelope], bool],
        timeout: float,  # noqa: ASYNC109  # public name is `timeout` (arch-adapters-factories §6.3)
    ) -> Envelope:
        if timeout < 0:
            raise ValueError("timeout must be >= 0")
        consumer = self._consumer
        if consumer is None:
            raise RuntimeError("KafkaEventReader is not started")
        started = time.monotonic()
        deadline = started + timeout
        while True:
            found = _take(self._pending, topic, match)
            if found is not None:
                return found
            remaining = deadline - time.monotonic()
            if remaining < 0:
                break
            timeout_ms = 0 if remaining == 0 else max(1, int(remaining * 1000))
            _store(self._pending, await _poll(consumer, timeout_ms))
        elapsed = time.monotonic() - started
        raise PollTimeout(f"no matching {topic} event after {elapsed:.2f}s")


def _open_consumer(bootstrap: str, group_id: str, topics: tuple[str, ...]) -> object:
    return cast(
        object,
        AIOKafkaConsumer(
            *topics,
            bootstrap_servers=bootstrap,
            group_id=group_id,
            auto_offset_reset="latest",
            enable_auto_commit=True,
        ),
    )


async def _call(consumer: object, name: str, /, **kwargs: object) -> object:
    method = cast(Callable[..., Awaitable[object]], getattr(consumer, name))
    return await method(**kwargs)


async def _poll(consumer: object, timeout_ms: int) -> list[tuple[str, object]]:
    raw = await _call(consumer, "getmany", timeout_ms=timeout_ms)
    found: list[tuple[str, object]] = []
    for partition, messages in _batches(raw):
        topic = _attr(partition, "topic")
        if not isinstance(topic, str):
            continue
        for message in messages:
            found.append((topic, _attr(message, "value")))
    return found


def _batches(raw: object) -> list[tuple[object, Sequence[object]]]:
    if not isinstance(raw, dict):
        return []
    pairs: list[tuple[object, Sequence[object]]] = []
    for key, item in cast(dict[object, object], raw).items():
        if isinstance(item, list):
            pairs.append((key, cast(Sequence[object], item)))
    return pairs


def _attr(value: object, name: str) -> object:
    return cast(object, getattr(value, name))


def _take(
    pending: dict[str, list[Envelope]],
    topic: str,
    match: Callable[[Envelope], bool],
) -> Envelope | None:
    queued = pending.get(topic)
    if not queued:
        return None
    for index, envelope in enumerate(queued):
        if match(envelope):
            del queued[index]
            return envelope
    return None


def _store(pending: dict[str, list[Envelope]], records: list[tuple[str, object]]) -> None:
    for topic, value in records:
        pending[topic].append(_envelope(value))


def _envelope(value: object) -> Envelope:
    """Same rules as SUT_MAP: v1 object, other dict, or unknown."""
    parsed = _as_dict(value)
    if parsed is None:
        return Envelope(event_type="unknown")
    payload = parsed.get("payload")
    if parsed.get("version") == "v1" and "event_type" in parsed and isinstance(payload, dict):
        body = _string_keys(cast(object, payload))
        if body is not None:
            trace = parsed.get("trace_id")
            timestamp = parsed.get("timestamp")
            return Envelope(
                event_type=str(parsed["event_type"]),
                version="v1",
                trace_id=None if trace is None else str(trace),
                timestamp=timestamp if isinstance(timestamp, str) else None,
                payload=body,
            )
    return Envelope(event_type="unknown", payload=parsed)


def _as_dict(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return _string_keys(cast(object, value))
    if isinstance(value, bytes | bytearray):
        try:
            text = bytes(value).decode("utf-8")
        except UnicodeDecodeError:
            return None
        return _dict_from_json(text)
    if isinstance(value, str):
        return _dict_from_json(value)
    return None


def _dict_from_json(text: str) -> dict[str, object] | None:
    try:
        loaded = cast(object, json.loads(text))
    except json.JSONDecodeError:
        return None
    if not isinstance(loaded, dict):
        return None
    return _string_keys(cast(object, loaded))


def _string_keys(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    parsed: dict[str, object] = {}
    for key, item in cast(dict[object, object], value).items():
        if not isinstance(key, str):
            return None
        parsed[key] = item
    return parsed
