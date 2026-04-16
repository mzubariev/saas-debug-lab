import time

import httpx
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from saas_shared.prometheus_metrics import (
    kafka_processing_duration_seconds,
    otel_trace_id,
)

from .services.dispatcher_service import process_consumed_message


async def run_consumer_loop(
    consumer: AIOKafkaConsumer,
    producer: AIOKafkaProducer,
    http_client: httpx.AsyncClient,
) -> None:
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
