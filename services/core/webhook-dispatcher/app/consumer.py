import time

import httpx
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.structs import TopicPartition
from saas_shared.prometheus_metrics import (
    kafka_consumer_lag,
    kafka_partition_count,
    kafka_processing_duration_seconds,
    otel_trace_id,
)

from .core.config import settings
from .services.dispatcher_service import process_consumed_message


def _record_partition_counts(consumer: AIOKafkaConsumer, topics: tuple) -> None:
    """Set kafka_partition_count once at startup using consumer metadata.

    Called after ``consumer.start()`` so metadata is already fetched.
    Errors are silently ignored — metrics are best-effort at startup.
    """
    for topic in topics:
        try:
            partitions = consumer.partitions_for_topic(topic)
            if partitions:
                kafka_partition_count.labels(topic=topic).set(len(partitions))
        except Exception:
            pass


async def _update_consumer_lag(consumer: AIOKafkaConsumer, msg) -> None:
    """Update kafka_consumer_lag gauge for the partition of the just-consumed message.

    Called after each message so Prometheus always reflects recent lag.
    Any broker error is silently ignored to avoid disrupting message processing.
    """
    tp = TopicPartition(msg.topic, msg.partition)
    try:
        end_offsets = await consumer.end_offsets([tp])
        lag = max(0, end_offsets[tp] - (msg.offset + 1))
        kafka_consumer_lag.labels(
            topic=msg.topic,
            partition=str(msg.partition),
            group=settings.consumer_group,
        ).set(lag)
    except Exception:
        pass


async def run_consumer_loop(
    consumer: AIOKafkaConsumer,
    producer: AIOKafkaProducer,
    http_client: httpx.AsyncClient,
    topics: tuple,
) -> None:
    _record_partition_counts(consumer, topics)

    async for msg in consumer:
        t0 = time.perf_counter()
        tid = otel_trace_id()  # capture while span is active, before hand-off
        await process_consumed_message(msg, http_client, producer)
        elapsed = time.perf_counter() - t0
        exemplar = {"trace_id": tid} if tid else None
        if exemplar:
            kafka_processing_duration_seconds.labels(topic=msg.topic).observe(elapsed, exemplar)
        else:
            kafka_processing_duration_seconds.labels(topic=msg.topic).observe(elapsed)
        await _update_consumer_lag(consumer, msg)
