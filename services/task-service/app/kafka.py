import json

from aiokafka import AIOKafkaProducer
from fastapi import FastAPI

from .config import settings


async def start_kafka(app: FastAPI) -> None:

    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers
    )

    await producer.start()

    app.state.kafka = producer


async def stop_kafka(app: FastAPI) -> None:

    await app.state.kafka.stop()


async def publish_event(producer: AIOKafkaProducer, topic: str, payload: dict) -> None:

    value = json.dumps(payload).encode("utf-8")

    await producer.send_and_wait(topic, value)