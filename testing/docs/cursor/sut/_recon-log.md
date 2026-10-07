# P0 recon log (evidence; rarely needed)

Facts below come from the service code, `infra/nginx/nginx.conf`, `infra/docker-compose.yml`, and a scratch import on Python 3.14.6 (2026-10-05). Service images are `python:3.11-slim`. `docs/system-architechture/ARCHITECTURE.md` disagrees with this file in the places called out below; this file wins.

Scratch run: one venv, each service's `requirements.txt`, plus `shared[services]` (the Dockerfiles install that extra; the requirements files do not). Environment was the service `.env.example`, loaded by pydantic-settings from a copy of that file, or exported from it when the file has no inline comments. `httpx.ASGITransport` does not run lifespan, so `/openapi.json` does not connect to Postgres, Redis, or Kafka. Worker checks imported the entry module and did not call `main` / `run`.


## Run results

| Import | Result |
| --- | --- |
| `services/core/api-gateway` `app.main` | OK. OpenAPI 200. Threads: `OtelBatchSpanRecordProcessor`. `ddtrace` not in `sys.modules`. |
| `services/core/auth-service` `app.main` | OK. OpenAPI 200. Same OTEL thread. SQLAlchemy instrumentor skipped (see Hazards). |
| `services/core/task-service` `app.main` | OK, including empty `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` from its `.env.example`. OpenAPI 200. Same OTEL thread and SQLAlchemy skip. |
| `services/core/webhook-receiver` `app.main` | OK. OpenAPI 200. Same OTEL thread. |
| `services/external/external-service-simulator` `app.main` | OK when pydantic-settings reads `.env.example` (python-dotenv strips the inline comments). OpenAPI 200. Same OTEL thread. |
| `services/core/webhook-dispatcher` `app.run` | OK. No OTEL thread, no Kafka connect, `ddtrace` not loaded. `main()` is what binds metrics and connects. |
| `workers/notification-worker` `app.worker` | OK. No OTEL thread, no Kafka or SMTP connect. |
| `workers/scheduler-worker` `app.core.celery`, `app.tasks.webhook_tasks`, `app.tasks.cleanup_tasks` | OK. No OTEL thread, no Redis, Postgres, or Kafka connect. Import creates `/tmp/prometheus_multiproc_scheduler`. |
| `migrations` `alembic upgrade head --sql` from `migrations/` | OK. Revisions `0001` users, `0002` tasks. |
| `alembic upgrade head` with `POSTGRES_HOST=127.0.0.1` `POSTGRES_PORT=1` | `ConnectionRefusedError` from asyncpg. URL is built from `POSTGRES_*`. |

`/health` and `/ready` returned 200 on every FastAPI app without lifespan. `/metrics` returned 200 `text/plain; version=0.0.4` (httpx does not send the OpenMetrics Accept header). Gateway OpenAPI generation warned: duplicate operation IDs `proxy_auth_auth__path__put`, `proxy_tasks_root_tasks_delete`, `proxy_tasks_tasks__path__delete`, `proxy_webhooks_webhooks__path__delete`.

First structlog event after a successful import loads `ddtrace` (4.15.4, 144 submodules) via `saas_shared.logging._inject_dd_trace_context`. It did not add a thread and did not fail the log. Fresh pins from this venv, not from an image lock: SQLAlchemy 2.1.3, FastAPI 0.142.2, Pydantic 2.13.5, aiokafka 0.14.0, Celery 5.3.1, kafka-python 3.0.11, psycopg2-binary 2.9.13, asyncpg 0.31.0, httpx 0.28.1. `opentelemetry-instrumentation-sqlalchemy` 0.66b0 supports `sqlalchemy>=1.0,<2.1` and logged that 2.1.3 was not instrumented. `redis` 8.1.0 warned that the `asyncio` extra does not exist; `redis.asyncio` still imported.

## Moved out of the living maps (pre-P0.1)

The scratch paragraph above is the Datadog evidence. P0.1 removed `ddtrace`, `ddtrace-run`, `infra/docker-compose.datadog.yml`, and `_inject_dd_trace_context`. With the package absent, that processor added `dd_trace_error` to every log line. The living SUT maps no longer list that hazard.

Production-prep candidates that used to close `SUT_MAP_FULL.md` are applied and recorded in `_prep.md`: delete the `ddtrace` import together with the requirement; leave OpenTelemetry at import (tests set `OTLP_ENDPOINT=""`); require connection hosts with no Docker DNS default; add `WEBHOOK_BACKOFF_BASE`, `DLQ_REPLAY_INTERVAL_SECONDS`, and `CLEANUP_INTERVAL_SECONDS`; keep the metrics port as the worker readiness signal.
