# Known issues

## Defects

## Testability changes

- `infra/docker-compose.datadog.yml`, service `requirements.txt`, `saas_shared.logging`, `saas_shared.sentry_setup`, `saas_shared.telemetry`: removed Datadog (`ddtrace-run`, the `ddtrace` requirement, the log processor, and the Sentry hooks) so a missing package does not stamp `dd_trace_error` on every log line.
- Service and worker `Settings`, plus `migrations/alembic/env.py`: database host, Redis URL (including DB index), Kafka bootstrap, `WEBHOOK_URL`, JWT secret, SMTP host, gateway service URLs, and the simulator webhook URL are required environment variables. A missing variable fails settings load instead of falling back to a Docker DNS name. Lab `.env` files already set the previous values, so compose behaviour is unchanged. `OTLP_ENDPOINT` still defaults to the collector; tests clear it.

## Decisions since the plan
