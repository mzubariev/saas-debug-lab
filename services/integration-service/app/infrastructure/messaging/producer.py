import structlog
from aiokafka import AIOKafkaProducer
from fastapi import FastAPI
from saas_shared.kafka_envelope import encode_envelope_bytes
from saas_shared.kafka_trace import current_trace_id_for_kafka_envelope, otel_kafka_headers

from ...core.config import settings

logger = structlog.get_logger()


async def start_kafka_producer(app: FastAPI) -> None:
    producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
    await producer.start()
    app.state.kafka_producer = producer
    logger.info("kafka_producer_started", bootstrap=settings.kafka_bootstrap_servers)


async def stop_kafka_producer(app: FastAPI) -> None:
    await app.state.kafka_producer.stop()
    logger.info("kafka_producer_stopped")


async def publish_json(
    producer: AIOKafkaProducer,
    topic: str,
    payload: dict,
    *,
    event_type: str,
    trace_id: str | None = None,
) -> None:
    tid = trace_id if trace_id is not None else current_trace_id_for_kafka_envelope()
    value = encode_envelope_bytes(event_type, payload, trace_id=tid)
    await producer.send_and_wait(topic, value, headers=otel_kafka_headers())
