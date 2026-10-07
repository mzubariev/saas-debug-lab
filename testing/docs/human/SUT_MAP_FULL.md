# SUT map

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

## nginx (`infra/nginx/nginx.conf`)

Host `80:80`, image `nginx:1.25-alpine`. Upstream `api-gateway:8000`, keepalive 32. `proxy_connect_timeout 5s`, `proxy_send_timeout 10s`, `proxy_read_timeout 30s`. Buffering on, `proxy_buffer_size 16k`, `proxy_buffers 4 16k`, `proxy_busy_buffers_size 32k`. Forwards `Host` (`$http_host`), `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`. `limit_req_status 429`.

Zones are keyed by `$http_authorization`, not by client IP. Both zones use `10m`.

| Zone | Rate | Location | Burst |
| --- | --- | --- | --- |
| `api` | `20r/s` | `location /` | `burst=100` (no `nodelay`; excess is delayed) |
| `api` | `20r/s` | `location /webhooks/` | `burst=20 nodelay` |
| `api` | `20r/s` | `location /otel/` | `burst=20 nodelay`, `client_max_body_size 1m`, proxy to `otel-collector:4318` |
| `auth` | `5r/m` | `location /auth/token` only | `burst=3 nodelay` |
| none | | `location /auth/` (so `/auth/me`) | no `limit_req` |
| none | | `location /external/` | proxy to `external-service-simulator:8000/`, prefix stripped |

A request with no `Authorization` header has an empty zone key. nginx does not account requests with an empty key (limit_req_zone documentation), so unauthenticated requests, including `POST /auth/token` (a login carries no `Authorization` header), are effectively not limited, whatever the `5r/m` setting says. This is unverified empirically: the P6.2 edge test sends about 10 logins within a minute and expects no 429; if confirmed, record it as BUG-1 (the documentation claims 5 requests per minute). `/` and `/webhooks/` are separate locations; the longer prefix wins.

## Postgres, Redis, Kafka images

`infra/docker-compose.yml` service `postgres` uses image `postgres:15` (major 15; the tag is not minor-pinned). No host port is published. Command sets `shared_preload_libraries=pg_stat_statements`. Redis image `redis:7`, no host port. Kafka is `confluentinc/cp-kafka:7.5.0` plus `confluentinc/cp-zookeeper:7.5.0`. Listeners `PLAINTEXT://kafka:9092` and `PLAINTEXT_HOST://localhost:9093`; neither is published in this compose file.

There is no Flower service in `infra/docker-compose.yml`.

## JWT

Both `services/core/api-gateway/app/core/config.py` and `services/core/auth-service/app/core/config.py` default `jwt_secret` to `dev-secret-change-in-production` (`JWT_SECRET`). Algorithm is the literal `HS256` in `api-gateway/app/dependencies.py` (`jwt.decode`) and `auth-service/app/services/auth_service.py` (`jwt.encode` / `jwt.decode`). No issuer or audience. Access-token claims are `sub` (username), `role`, `exp`. Lifetime is `token_expire_minutes`, default 30 (`TOKEN_EXPIRE_MINUTES`). Gateway 401 bodies: `Missing authorization header`, `Token expired`, `Invalid token: {exc}`. Auth login 401 body is `Invalid credentials` for an unknown user and for a bad password. Auth decode 401 bodies match the gateway (`Token expired`, `Invalid token: {exc}`).

## Seed users

Migrations do not insert users. `scripts/seed_dev.py` is manual. It reads `DATABASE_URL`, default `postgresql://admin:admin@localhost:5432/saas`, connects with `psycopg` (v3), and hashes with passlib argon2. Users, inserted `ON CONFLICT (username) DO NOTHING`: `admin` / `admin123` role `admin`, `user` / `user123` role `user`. Ten tasks use fixed UUIDs `11111111-0000-0000-0000-000000000001` through `...0010`.

## Kafka envelope (`shared/saas_shared/kafka_envelope.py`)

`build_envelope` / `encode_envelope_bytes` write `event_type`, `version` (`v1`), `trace_id` (argument, else `uuid4().hex`), `timestamp` (UTC ISO), `payload`. `parse_envelope_message` returns `(event_type, payload, trace_id)` for a v1 object whose `payload` is a dict. Anything else that is a dict becomes `("unknown", that_dict, None)`. Invalid JSON, non-dict JSON, bytes that are not UTF-8 JSON, and other types become `("unknown", {}, None)`.

| Topic | event_type | Producer | Consumer |
| --- | --- | --- | --- |
| `task_created` | `task.created` | task-service | notification-worker group `notification-worker`; webhook-dispatcher group `webhook-dispatcher` |
| `task_updated` | `task.updated` | task-service | webhook-dispatcher only |
| `webhook_inbound` | `webhook.inbound` | webhook-receiver (`TOPIC_WEBHOOK_INBOUND`, default `webhook_inbound`) | none in this repo |
| `webhook_dlq` | `webhook.dlq` | webhook-dispatcher | scheduler-worker group `scheduler-worker` |

Task payload fields are `id`, `title`, `status`. Inbound payload is `event`, `data`. DLQ payload is the business payload plus `error`, `attempts`, `timestamp`. Producers also set W3C headers via `otel_kafka_headers` and, on task-service, `sentry-trace` and `baggage`.

## saas_shared (`shared/saas_shared`)

Installed in every Python image as `pip install -e /app/shared[services]` (migrations install the base package only). Base dependencies are structlog and `sqlalchemy>=2.0`. The `services` extra adds fastapi, prometheus-client, `redis[asyncio]`, the OTEL SDK, FastAPI/httpx/SQLAlchemy/Redis instrumentors, and `opentelemetry-exporter-otlp-proto-grpc`.

| Module | Role |
| --- | --- |
| `health.py` | `GET /health` → `{"status":"ok"}`, `GET /ready` → `{"status":"ready"}`. Neither checks a dependency. |
| `metrics.py` | `GET /metrics`, `include_in_schema=False`. OpenMetrics when `Accept` contains `application/openmetrics-text`, else Prometheus text. |
| `prometheus_metrics.py` | Process-global counters, histograms, gauges. Import sets `machine_cpu_cores` and `container_memory_limit_bytes` (0 when cgroup files are absent). |
| `prometheus_http.py` | HTTP middleware. Path label replaces UUIDs and integer segments with `{id}` and strips a trailing slash. Skips `/metrics`. |
| `telemetry.py` | `setup_telemetry` / `setup_worker_telemetry` build a `TracerProvider`, `BatchSpanProcessor`, and OTLP gRPC exporter unless `DD_TRACE_ENABLED` is `1`/`true`/`yes`/`on` (`tracing_env.py`). With the flag unset, FastAPI setup also calls `FastAPIInstrumentor.instrument_app`. An empty `otlp_endpoint` skips the exporter and still installs the client instrumentors. |
| `sentry_setup.py` | Empty `dsn` returns before `sentry_sdk.init`. `traces_sample_rate=0.1` when a DSN is set. |
| `logging.py` | `setup_logging` configures structlog JSON on stdout. The `ddtrace` import runs inside the processor, the first time a log event is rendered. |
| `redis_cache.py` | `start_redis` sets `app.state.redis`. Cache get/set/delete swallow errors and log a warning. |
| `models/` | `User` table `users` (`id`, `username` unique, `hashed_password`, `role` default `user`). `Task` table `tasks` (`id` UUID, `title`, `status` enum `taskstatus`: `created`, `in_progress`, `completed`, `created_at`, `updated_at`). Indexes `ix_tasks_status`, `ix_tasks_created_at`. |

`ddtrace` is not imported by `setup_telemetry`. Base Dockerfiles run uvicorn or `python -m` with no `ddtrace-run`. `infra/docker-compose.datadog.yml` is the file that prefixes commands with `ddtrace-run`.

## migrations (`migrations/`)

`alembic.ini` has no `sqlalchemy.url`. `script_location = alembic` is relative to the cwd (the image `WORKDIR` is `/app`). `alembic/env.py` builds `postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}`. `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` are required. `POSTGRES_HOST` defaults to `postgres`, `POSTGRES_PORT` to `5432`. It does not read `DATABASE_URL`. Online mode uses an async engine and `pool.NullPool`. Compose service `migrations` runs `alembic upgrade head` once (`restart: "no"`) after postgres is healthy. Head is `0002`. No seed in the revisions.

## Connection settings (env vs code default)

"Required" means `Settings()` raises if the variable is missing. A default means a hard-coded host is used when the variable is unset. None of these are read from a single `DATABASE_URL` inside the services (only `scripts/seed_dev.py` uses `DATABASE_URL`).

| Setting | api-gateway | auth-service | task-service | webhook-receiver | dispatcher | notification-worker | scheduler-worker |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Postgres | none | required `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`; port default 5432. DSN `postgresql+asyncpg` | same shape, all four required, no `service_name` default | none | none | none | same four required; DSN `postgresql+psycopg2`; port default 5432 |
| Redis | none | `REDIS_URL` default `redis://redis:6379/1` | `REDIS_URL` default `redis://redis:6379/0` | none | none | none | `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` default `redis://redis:6379/2` |
| Kafka | none | none | `KAFKA_BOOTSTRAP_SERVERS` required, no default | default `kafka:9092` | default `kafka:9092` | required, no default | default `kafka:9092` |
| `WEBHOOK_URL` | none | none | none | none | default `http://nginx/external/receive-webhook` | none | same default |
| `JWT_SECRET` | default `dev-secret-change-in-production` | same default | none | none | none | none | none |
| SMTP host | none | none | none | none | none | `SMTP_HOST` default `toxiproxy`, port default `11025` | none |

Other URL defaults: gateway `AUTH_SERVICE_URL` `http://auth-service:8000`, `INTEGRATION_SERVICE_URL` `http://webhook-receiver:8000`, `TASK_SERVICE_URL` required. Simulator `INTEGRATION_SERVICE_WEBHOOK_URL` default `http://localhost/webhooks/inbound`. Every FastAPI service, webhook-dispatcher, and both workers default `OTLP_ENDPOINT` to `http://otel-collector:4317`. Alembic host default is `postgres` (table above does not apply).

## Hard-coded timings

| What | Where | Value | Env? |
| --- | --- | --- | --- |
| Gateway HTTP timeout | `api-gateway` `gateway_timeout` | 5.0 s | `GATEWAY_TIMEOUT` |
| Access-token TTL | auth `token_expire_minutes` | 30 min | `TOKEN_EXPIRE_MINUTES` |
| User cache | auth `auth_service._USER_CACHE_TTL`, key `user:{username}` | 300 s | no |
| Task list / item cache | task `TaskService` | 60 s key `tasks:list`; 120 s key `tasks:{id}` | no |
| Dispatcher attempts | `max_retries` | 3 | `MAX_RETRIES` |
| Dispatcher backoff | `dispatcher_service._BACKOFF_BASE` | after attempt `n` (when `n < max_retries`): sleep `1.0 * 2^(n-1)` seconds plus `random.uniform(0, backoff * 0.1)` (zero to +10%, not ±10%). Default 3 attempts sleep ~1 s then ~2 s. No 4 s sleep unless `MAX_RETRIES` ≥ 4 | base and jitter are not env |
| Dispatcher HTTP timeout | `webhook_timeout` | 10 s | `WEBHOOK_TIMEOUT` |
| Simulator inbound POST | `routes._send_with_retry` | timeout 10 s; sleep `delay * 2**attempt` between tries. Query `delay` default 1.0, `retry` default 0 | no |
| Beat | `scheduler` `celery.py` `beat_schedule` | `retry_failed_webhooks` every 60.0 s; `cleanup_old_tasks` every 300.0 s | no |
| DLQ drain caps | `webhook_retry_service` | 200 messages, 20 s wall, consumer `consumer_timeout_ms=5000` | no |
| Celery DLQ HTTP retry | `retry_single_webhook` | `autoretry_for=(httpx.RequestError,)`, `max_retries=5`, `retry_backoff=True`, `retry_backoff_max=300`, `acks_late=True`. Any `HTTPStatusError` (4xx and 5xx) is permanent | no |
| Cleanup age | `cleanup_completed_tasks_minutes` | 5 minutes. `0` disables. Column compare is `updated_at < now - minutes`. Not hours | `CLEANUP_COMPLETED_TASKS_MINUTES` |
| Cleanup Celery retry | `cleanup_tasks.py` | `max_retries=3`, `default_retry_delay=60` | no |
| Metrics port | dispatcher, notification, scheduler | 9100 | `METRICS_PORT` |

## api-gateway

Directory `services/core/api-gateway`. Entrypoint `app.main:app` (uvicorn `:8000`, not published). No startup handler. Import calls `setup_logging`, `setup_sentry_fastapi` (`httpx=True`), `setup_telemetry`, then constructs `httpx.AsyncClient(timeout=gateway_timeout)` in `app/infrastructure/http/client.py`. That client is never closed.

Routes in `app/api/routes/proxy.py` (no response models). OpenAPI paths: `GET,POST,PUT,DELETE /auth/{path}`; `GET,POST,PUT,PATCH,DELETE /tasks` and `/tasks/{path}`; `GET,POST,PUT,PATCH,DELETE /webhooks/{path}`; plus `/health` and `/ready`. `/tasks` and `/tasks/{path}` depend on `verify_token` (`HTTPBearer`, `auto_error=False`). `/auth/*` and `/webhooks/*` do not. Proxy drops headers `host`, `sentry-trace`, `baggage`, `traceparent`, `tracestate`. Downstream timeout → 504 `Downstream timeout`. Other `httpx.RequestError` → 502 `Downstream unavailable`. Upstream status and body are passed through. Compose healthcheck: Python `urllib` `GET http://localhost:8000/health` (this image has no curl).

## auth-service

Directory `services/core/auth-service`. Import builds `create_async_engine(postgres_dsn)` and calls `setup_telemetry` plus `instrument_sqlalchemy_async_engine`. No connection until the engine is used. `@app.on_event("startup")` calls `start_redis` (`app.state.redis`); shutdown closes it.

| Method | Path | Request | Response | Auth |
| --- | --- | --- | --- | --- |
| POST | `/auth/token` | `application/x-www-form-urlencoded` `OAuth2PasswordRequestForm` (`username`, `password`). Schema `Body_login_auth_token_post` | `TokenResponse` `access_token`, `token_type` default `bearer` (`app/schemas/auth.py`) | none |
| GET | `/auth/me` | `OAuth2PasswordBearer` tokenUrl `/auth/token` | `UserInfo` `username`, `role` | Bearer. Decode only; no database read |

DI: `get_db` yields `SessionLocal` (`app/dependencies.py`). `get_auth_service` builds `AuthService(db, request.app.state.redis)`. Passwords: passlib argon2 (`app/security.py`). Cache JSON stores `username`, `hashed_password`, `role`. Compose healthcheck: `curl -f http://localhost:8000/health`. Depends on postgres, redis, and migrations completed.

## task-service

Directory `services/core/task-service`. Same async engine-at-import pattern as auth (`postgresql+asyncpg`). Startup connects Kafka (`AIOKafkaProducer.start`, `app.state.kafka`) and Redis. Shutdown stops both. No JWT check in this service.

Routes `app/api/routes/tasks.py`, models `app/schemas/task.py` (`TaskCreate.title`, `TaskOut` id/title/status/created_at/updated_at). OpenAPI: `GET,POST /tasks`, `GET /tasks/{task_id}`, `PATCH /tasks/{task_id}/start`, `PATCH /tasks/{task_id}/complete`. `POST /tasks` is 201. DI: `get_db`; `get_task_service` passes `app.state.redis` and `app.state.kafka`. Repository commits inside `create` and `save`.

Transitions: `start` only from `created`, `complete` only from `in_progress`. Else 409 `Cannot start task in status '{status}'. Expected 'created'.` or the complete equivalent with `in_progress`. Missing row: 404 `Task not found`. A cache hit returns the stored JSON dict; a miss returns the ORM row. `response_model` is `TaskOut` either way. Publish happens after the DB commit, then the list key (and the item key on transition) is deleted. Compose healthcheck curls `:8000/health`. Depends on postgres, kafka, redis, migrations.

## webhook-receiver

Directory `services/core/webhook-receiver`. Startup only: `AIOKafkaProducer` on `app.state.kafka_producer`. No database or Redis.

`POST /webhooks/inbound` (`app/api/routes/webhooks.py`), body `WebhookPayload` (`event: str`, `data: dict` default `{}`), status 200, body `{"status":"received","event": ...}`. No auth. Publish failure is logged and re-raised. Compose healthcheck curls `:8000/health`. Depends on kafka healthy.

## external-service-simulator

Directory `services/external/external-service-simulator`. No startup handler, no database, Redis, or Kafka. Host port `8000:8000`. In-memory set `_processed_keys` lives in the process.

| Method | Path | Request | Behaviour |
| --- | --- | --- | --- |
| POST | `/receive-webhook` | JSON object (free-form). Query `fail_rate` 0..1, `delay` ≥ 0, `status` int, all optional | `Idempotency-Key` already stored → 200 `{"status":"duplicate","idempotency_key":...}` before delay. Else sleep `delay`, then `random.random() < fail_rate` → 500 `{"status":"error","reason":"simulated_failure"}` (key not stored). Else non-200 `status` → that code `{"status":"custom_status","code":...}` (key not stored). Else 200 `{"status":"received","payload":...}` and the key is stored. Defaults from settings: fail 0.0, delay 0.0, status 200. |
| POST | `/trigger-event` | `InboundTrigger` `event`, `data` default `{}`. Query `retry` default 0, `delay` default 1.0 | 202 `{"status":"triggered","event":...}` immediately. Background `httpx.AsyncClient.post` to `integration_service_webhook_url`. |

Compose healthcheck curls `:8000/health`. No `depends_on`.

## webhook-dispatcher

Directory `services/core/webhook-dispatcher` (not `workers/`). No FastAPI app. Entry `python -m app.run` → `main()`. `main` calls `setup_logging`, `setup_worker_telemetry`, `setup_sentry_worker`, `start_http_server(metrics_port)`, then `_async_main` (producer, `httpx.AsyncClient`, consumer). Import of `app.run` does not do that; it does register Prometheus metrics because `consumer` imports `dispatcher_service`.

Consumer: `AIOKafkaConsumer` on `task_created` and `task_updated` (`CONSUME_TOPICS`, not env), `group_id` default `webhook-dispatcher`, `auto_offset_reset=earliest`. Each POST sends `Idempotency-Key` set to `str(payload.get("id", ""))`. 4xx stops and writes the DLQ. 5xx and `httpx.RequestError` retry. Permanent failure produces to `webhook_dlq`. Produce errors are logged and swallowed. There is no compose healthcheck and no published port. Depends on kafka and external-service-simulator healthy. Readiness that exists in code is `GET /metrics` on `METRICS_PORT` after `main()` has started the server.

## notification-worker

Directory `workers/notification-worker`. Entry `python -m app.worker` → `run()`, which is the first call to telemetry, Sentry, and `start_http_server`. Import of `app.worker` only builds `Settings` (so `KAFKA_BOOTSTRAP_SERVERS` must be set) and registers Prometheus metrics. `tenacity` is in `requirements.txt` and is not imported.

Consumer group `notification-worker`, topic `task_created` only, `auto_offset_reset=earliest`. SMTP via `aiosmtplib.send` to `smtp_host` / `smtp_port`, TLS flags `SMTP_USE_TLS` and `SMTP_USE_STARTTLS` default false. From/to default `notifications@saas-debug-lab.local` and `change-me@emailhook.site`. MIME alternative, plain plus HTML. `SMTPException` and `OSError` are counted and logged, not re-raised, so the consumer continues. No email retry. Compose sets `SMTP_HOST` default `toxiproxy` and does not healthcheck this service. Depends on kafka only. Metrics port 9100 inside `run()`.

## scheduler-worker

Directory `workers/scheduler-worker`. Compose command: `celery -A app.core.celery:celery_app worker --beat --loglevel=info --concurrency=2 --prefetch-multiplier=1`. No HTTP app and no compose healthcheck. Depends on redis, postgres, kafka, migrations.

Import of `app.core.celery` (before any broker connection) does all of the following: `setdefault PROMETHEUS_MULTIPROC_DIR` to `/tmp/prometheus_multiproc_scheduler` and `os.makedirs` it; `setup_logging`; `setup_sentry_celery` (no-op if DSN empty); `CeleryInstrumentor().instrument()`. It does not call `setup_worker_telemetry`. That, a second Sentry init, SQLAlchemy sync instrumentation, and the metrics HTTP server run in `worker_process_init`. With the multiproc dir set, only the child that takes `metrics_http.lock` binds `METRICS_PORT`. The parent `--beat` process does not bind it.

`retry_failed_webhooks` (every 60 s) imports kafka-python at import of `app.tasks.webhook_tasks` (`from kafka.errors import KafkaTimeoutError` and `KafkaConsumer` via `infrastructure/kafka/consumer.py`) but constructs the consumer only inside the task. Consumer: topic `webhook_dlq`, group `scheduler-worker`, `enable_auto_commit=True`, `auto_offset_reset=earliest`, `value_deserializer` JSON. Each message is `retry_single_webhook.delay(...)` after dropping the `error` field; `attempts` and `timestamp` stay on the body. `post_json_sync` is `httpx.Client.post` with no `Idempotency-Key`. `cleanup_old_tasks` uses a sync SQLAlchemy engine, `pool_pre_ping=True`, created on first use (`get_sync_engine`), driver psycopg2 through the DSN. SQL: `DELETE FROM tasks WHERE status = 'completed' AND updated_at < :cutoff`.

## Clients

| Process | Database | Kafka | HTTP |
| --- | --- | --- | --- |
| auth, task | SQLAlchemy 2 async + asyncpg. Engine object at import | task: aiokafka producer at startup | none |
| webhook-receiver, dispatcher | none | aiokafka producer and (dispatcher) consumer, both inside startup / `main` | dispatcher: `httpx.AsyncClient` |
| notification-worker | none | aiokafka consumer inside `consume()` | `aiosmtplib` |
| scheduler-worker | SQLAlchemy sync + psycopg2, lazy engine | kafka-python `KafkaConsumer`, per DLQ tick | `httpx.Client` per POST |
| migrations | asyncpg via Alembic | none | none |
| seed script | psycopg v3 | none | none |

## Readiness

| Process | Compose check | What the code actually exposes |
| --- | --- | --- |
| api-gateway, auth, task, webhook-receiver, simulator | `GET :8000/health` | `/health` and `/ready` are static JSON. They do not ping Postgres, Redis, or Kafka. Dependency connections are `@app.on_event("startup")` (gateway and simulator have no such handler). |
| webhook-dispatcher, notification-worker | none | `prometheus_client.start_http_server` on `METRICS_PORT` (default 9100) at the start of `main` / `run`, then the consume loop. Not bound at import. |
| scheduler-worker | none | Same port, but only in one prefork child (`worker_process_init`), not in the beat parent and not at import. |
| migrations | `service_completed_successfully` | process exit 0 |

`ASGITransport` does not run `on_event`, so a test that needs Redis or Kafka must enter the app lifespan itself. `get_db` closes over the module-level `SessionLocal` built from the environment at import.

## Hazards

- nginx limits by the `Authorization` value. One shared bearer token is one `20r/s` bucket on `location /`. `/auth/token` carries no `Authorization` header, so its key is empty and nginx does not account it: the `5r/m` limit is probably inactive (BUG-1 candidate, confirm in P6.2). `/auth/me` is not limited. `/webhooks/` is `20r/s` burst 20 `nodelay`, not the `location /` burst of 100.
- `GET /ready` stays 200 when Redis, Kafka, or Postgres is down. Compose treats that as healthy for the FastAPI services.
- Importing any FastAPI `app.main` starts `OtelBatchSpanRecordProcessor` and it tries `OTLP_ENDPOINT` (`http://otel-collector:4317` if unset). The scratch run logged `StatusCode.UNAVAILABLE` for that DNS name after `/openapi.json`.
- `ddtrace` is not loaded by `import app.main`. The first structlog line imports it when the package is installed. If the package is absent, `_inject_dd_trace_context` catches the error and adds `dd_trace_error` to that log line.
- Every service package is named `app`. Two services cannot be imported in one process. `prometheus_metrics` registers global collectors at import. Scheduler import sets `PROMETHEUS_MULTIPROC_DIR` and creates that directory.
- `requirements.txt` does not pin SQLAlchemy and does not list the OTEL SDK. This venv resolved SQLAlchemy 2.1.3, and the SQLAlchemy instrumentor then instrumented nothing. Import still succeeded. Images only import because the Dockerfile installs `shared[services]`.
- Gateway OpenAPI has duplicate operation IDs (warning, HTTP 200).
- Dispatcher backoff is `1 * 2^(attempt-1)` plus 0..10% and, with the default 3 attempts, waits twice (~1 s, ~2 s). Scheduler DLQ replay does not send `Idempotency-Key`, and it treats 5xx as final. Notification SMTP failures are swallowed. `tenacity` is unused.
- User cache stores `hashed_password` for 300 s. Task cache returns dicts on hit and ORM rows on miss.
- `scripts/seed_dev.py` is not run by compose. Postgres is not published, so the script's default `localhost:5432` does not match this compose file.
- Alembic `script_location` is relative to the cwd. Running it outside `migrations/` fails with `Path doesn't exist: alembic` before it connects.

## Production-prep candidates

Behaviour-neutral seams that would remove the obstacles above. Not done in this task.

1. Delete the `ddtrace` import in `saas_shared.logging` (and the Sentry `ddtrace` hooks) in the same change as dropping the requirement and `ddtrace-run`. Uninstalling the package alone makes every log line carry `dd_trace_error`.
2. Call `setup_telemetry` inside lifespan / `main` / `worker_process_init`. An empty `otlp_endpoint` already skips the exporter, but the default is `http://otel-collector:4317`, so import starts `BatchSpanProcessor`. Sentry is already inert when `SENTRY_DSN` is empty. Kafka and Redis already connect only in startup / `main`, not at import.
3. Remove hard-coded hosts so a missing variable fails `Settings()` instead of pointing at Docker DNS: Redis DB 0/1/2 URLs, Kafka `kafka:9092`, both `WEBHOOK_URL`s, both `JWT_SECRET`s, `SMTP_HOST`, gateway `AUTH_SERVICE_URL` and `INTEGRATION_SERVICE_URL`, simulator `INTEGRATION_SERVICE_WEBHOOK_URL`, Alembic's `POSTGRES_HOST` default. `TASK_SERVICE_URL` and notification `KAFKA_BOOTSTRAP_SERVERS` are already required.
4. Env knobs, current numbers as defaults: dispatcher `_BACKOFF_BASE` (and the 10% jitter cap), beat `60.0` and `300.0`. `MAX_RETRIES`, `WEBHOOK_TIMEOUT`, and `CLEANUP_COMPLETED_TASKS_MINUTES` (default 5, not an hour setting) already exist. Cache TTLs 300/60/120 and the DLQ caps (200, 20 s, 5000 ms) are still literals.
5. Compose healthchecks already curl `/health` for the five FastAPI services. Dispatcher and notification-worker bind `:9100/metrics` at the start of `main` / `run`; scheduler binds it only in one prefork child. A metrics-port check is the readiness signal those three have. Migrations stays "exit 0".
