from aiokafka import AIOKafkaProducer
from fastapi import FastAPI
from .config import settings


async def start_kafka(app: FastAPI):

    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers
    )

    await producer.start()

    app.state.kafka = producer


async def stop_kafka(app: FastAPI):

    await app.state.kafka.stop()