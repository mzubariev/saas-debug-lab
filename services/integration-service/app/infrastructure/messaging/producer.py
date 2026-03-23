import structlog
from aiokafka import AIOKafkaProducer
from fastapi import FastAPI
from saas_shared.kafka_envelope import encode_envelope_bytes

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
) -> None:
    value = encode_envelope_bytes(event_type, payload)
    await producer.send_and_wait(topic, value)
