import asyncio
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import structlog
from aiokafka import AIOKafkaConsumer

from .config import settings
from .logging import setup_logging


logger = structlog.get_logger()

TOPIC = "task_created"
GROUP_ID = "notification-worker"


def _build_message(event: dict) -> MIMEMultipart:
    task_id = event.get("id", "unknown")
    title = event.get("title", "Untitled")
    status = event.get("status", "created")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[SaaS Debug Lab] Task created: {title}"
    msg["From"] = settings.email_from
    msg["To"] = settings.email_to

    plain = (
        f"A new task has been created.\n\n"
        f"Title:  {title}\n"
        f"ID:     {task_id}\n"
        f"Status: {status}\n"
    )
    html = (
        "<html><body>"
        "<h2>New Task Created</h2>"
        "<table>"
        f"<tr><td><b>Title</b></td><td>{title}</td></tr>"
        f"<tr><td><b>ID</b></td><td>{task_id}</td></tr>"
        f"<tr><td><b>Status</b></td><td>{status}</td></tr>"
        "</table>"
        "</body></html>"
    )

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))
    return msg


async def _send_email(msg: MIMEMultipart) -> None:
    """Deliver the message via SMTP. Raises on any transport error."""
    smtp_kwargs: dict = {
        "hostname": settings.smtp_host,
        "port": settings.smtp_port,
        "use_tls": settings.smtp_use_tls,
        "start_tls": settings.smtp_use_starttls,
    }

    if settings.smtp_username and settings.smtp_password:
        smtp_kwargs["username"] = settings.smtp_username
        smtp_kwargs["password"] = settings.smtp_password

    await aiosmtplib.send(msg, **smtp_kwargs)


async def handle_event(event: dict) -> None:
    task_id = event.get("id")
    title = event.get("title")
    msg = _build_message(event)

    try:
        await _send_email(msg)
        logger.info(
            "notification_sent",
            task_id=task_id,
            title=title,
            to=settings.email_to,
            smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port,
        )
    except aiosmtplib.SMTPException as exc:
        logger.error(
            "smtp_delivery_failed",
            task_id=task_id,
            title=title,
            to=settings.email_to,
            error=str(exc),
        )
    except OSError as exc:
        # Covers connection-refused, DNS failure, TCP reset — real infra failures.
        logger.error(
            "smtp_connection_failed",
            task_id=task_id,
            smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port,
            error=str(exc),
        )


async def consume() -> None:
    consumer = AIOKafkaConsumer(
        TOPIC,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=GROUP_ID,
        auto_offset_reset="earliest",
    )

    await consumer.start()

    logger.info("consumer_started", topic=TOPIC, group_id=GROUP_ID)

    try:
        async for msg in consumer:
            try:
                event = json.loads(msg.value.decode("utf-8"))
                await handle_event(event)
            except Exception as exc:
                logger.error(
                    "event_processing_failed",
                    error=str(exc),
                    topic=msg.topic,
                    offset=msg.offset,
                )
    finally:
        await consumer.stop()


def run() -> None:
    setup_logging(settings.log_level, settings.service_name)
    asyncio.run(consume())


if __name__ == "__main__":
    run()
