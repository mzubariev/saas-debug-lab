import asyncio
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import sentry_sdk
import structlog
from aiokafka import AIOKafkaConsumer
from saas_shared.kafka_envelope import parse_envelope_message

from .config import settings
from .logging import setup_logging


logger = structlog.get_logger()

TOPIC    = "task_created"
GROUP_ID = "notification-worker"


def _setup_sentry() -> None:
    """Initialise Sentry error tracking. No-op when SENTRY_DSN is not set.

    The worker has no ASGI layer, so we use the plain SDK without FastAPI /
    Starlette integrations.  Exceptions are captured explicitly with
    sentry_sdk.capture_exception() at each failure point so that every SMTP
    or connection error appears as a separate Sentry issue, enriched with the
    task_id and email recipient that caused it.
    """
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
    sentry_sdk.set_tag("service", settings.service_name)
    sentry_sdk.set_tag("worker", "notification-worker")


def _build_message(event: dict) -> MIMEMultipart:
    task_id = event.get("id", "unknown")
    title   = event.get("title", "Untitled")
    status  = event.get("status", "created")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[SaaS Debug Lab] Task created: {title}"
    msg["From"]    = settings.email_from
    msg["To"]      = settings.email_to

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
        "hostname":  settings.smtp_host,
        "port":      settings.smtp_port,
        "use_tls":   settings.smtp_use_tls,
        "start_tls": settings.smtp_use_starttls,
    }

    if settings.smtp_username and settings.smtp_password:
        smtp_kwargs["username"] = settings.smtp_username
        smtp_kwargs["password"] = settings.smtp_password

    await aiosmtplib.send(msg, **smtp_kwargs)


async def handle_event(event: dict) -> None:
    task_id = event.get("id")
    title   = event.get("title")
    msg     = _build_message(event)

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
        # Use push_scope so extra context is isolated to this single capture
        # and does not bleed into events from other Kafka messages.
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("task_id",    task_id or "unknown")
            scope.set_tag("error_type", "smtp_protocol")
            scope.set_extra("task_title",  title)
            scope.set_extra("smtp_host",   settings.smtp_host)
            scope.set_extra("smtp_port",   settings.smtp_port)
            scope.set_extra("recipient",   settings.email_to)
            sentry_sdk.capture_exception(exc)

    except OSError as exc:
        # Connection-refused, DNS failure, TCP reset, Toxiproxy chaos.
        logger.error(
            "smtp_connection_failed",
            task_id=task_id,
            smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port,
            error=str(exc),
        )
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("task_id",    task_id or "unknown")
            scope.set_tag("error_type", "smtp_connection")
            scope.set_extra("task_title",  title)
            scope.set_extra("smtp_host",   settings.smtp_host)
            scope.set_extra("smtp_port",   settings.smtp_port)
            scope.set_extra("recipient",   settings.email_to)
            sentry_sdk.capture_exception(exc)


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
            # Extract Sentry trace context that was stamped onto the Kafka
            # message by task-service at publish time.  Calling
            # continue_trace() creates a new transaction that is linked to the
            # same trace_id as the originating browser request, so the full
            # Browser → Gateway → task-service → notification-worker chain
            # appears as a single distributed trace in Sentry.
            incoming_trace_headers = {
                k.lower(): v.decode("utf-8", errors="replace")
                for k, v in (msg.headers or [])
                if k.lower() in ("sentry-trace", "baggage")
            }
            transaction = sentry_sdk.continue_trace(
                incoming_trace_headers,
                op="queue.process",
                name=f"consume {msg.topic}",
            )

            with sentry_sdk.start_transaction(transaction) as tx:
                tx.set_data("messaging.system", "kafka")
                tx.set_data("messaging.destination", msg.topic)
                tx.set_data("messaging.kafka.offset", msg.offset)

                try:
                    raw = json.loads(msg.value.decode("utf-8"))
                    _event_type, event = parse_envelope_message(raw)
                    tx.set_data("task.id", event.get("id"))
                    tx.set_data("kafka.event_type", _event_type)
                    await handle_event(event)
                except Exception as exc:
                    logger.error(
                        "event_processing_failed",
                        error=str(exc),
                        topic=msg.topic,
                        offset=msg.offset,
                    )
                    # Capture unexpected exceptions (JSON decode errors, etc.)
                    # that are not already handled inside handle_event().
                    with sentry_sdk.push_scope() as scope:
                        scope.set_tag("error_type", "event_processing")
                        scope.set_extra("kafka_topic",  msg.topic)
                        scope.set_extra("kafka_offset", msg.offset)
                        sentry_sdk.capture_exception(exc)
    finally:
        await consumer.stop()


def run() -> None:
    setup_logging(settings.log_level, settings.service_name)
    _setup_sentry()
    asyncio.run(consume())


if __name__ == "__main__":
    run()
