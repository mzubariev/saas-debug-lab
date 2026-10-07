# notification-worker (SUT facts)

Directory `workers/notification-worker`. Entry `python -m app.worker` → `run()`, which is the first call to telemetry, Sentry, and `start_http_server`. Import of `app.worker` only builds `Settings` (so `KAFKA_BOOTSTRAP_SERVERS` must be set) and registers Prometheus metrics. `tenacity` is in `requirements.txt` and is not imported.

Consumer group `notification-worker`, topic `task_created` only, `auto_offset_reset=earliest`. SMTP via `aiosmtplib.send` to `smtp_host` / `smtp_port`, TLS flags `SMTP_USE_TLS` and `SMTP_USE_STARTTLS` default false. From/to default `notifications@saas-debug-lab.local` and `change-me@emailhook.site`. MIME alternative, plain plus HTML. `SMTPException` and `OSError` are counted and logged, not re-raised, so the consumer continues. No email retry. `SMTP_HOST` is required in `Settings` (no code default). Compose still interpolates `SMTP_HOST: ${SMTP_HOST:-toxiproxy}`. This service has no compose healthcheck. Depends on kafka only. Metrics port 9100 inside `run()`.

Common facts (nginx, JWT, envelope, settings, timings, readiness, hazards): `testing/docs/cursor/sut/SUT_MAP.md`.
