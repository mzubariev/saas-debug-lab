# webhook-receiver (SUT facts)

Directory `services/core/webhook-receiver`. Startup only: `AIOKafkaProducer` on `app.state.kafka_producer`. No database or Redis.

`POST /webhooks/inbound` (`app/api/routes/webhooks.py`), body `WebhookPayload` (`event: str`, `data: dict` default `{}`), status 200, body `{"status":"received","event": ...}`. No auth. Publish failure is logged and re-raised. Compose healthcheck curls `:8000/health`. Depends on kafka healthy.

Common facts (nginx, JWT, envelope, settings, timings, readiness, hazards): `testing/docs/SUT_MAP.md`.
