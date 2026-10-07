# SUT map (common facts)

Split into files for token economy. This file: facts shared by several services. One file per service: `testing/docs/cursor/sut/<service>.md` (attach only the service(s) a task touches). `testing/docs/cursor/sut/_prep.md`: production-prep candidates (P0.1 only). `testing/docs/cursor/sut/_recon-log.md`: evidence of the P0 scratch run (rarely needed).

Facts below come from the service code, `infra/nginx/nginx.conf`, `infra/docker-compose.yml`, and a scratch import on Python 3.14.6 (2026-10-05). Service images are `python:3.11-slim`. `docs/system-architechture/ARCHITECTURE.md` disagrees with this file in the places called out below; this file wins.

Scratch run: one venv, each service's `requirements.txt`, plus `shared[services]` (the Dockerfiles install that extra; the requirements files do not). Environment was the service `.env.example`, loaded by pydantic-settings from a copy of that file, or exported from it when the file has no inline comments. `httpx.ASGITransport` does not run lifespan, so `/openapi.json` does not connect to Postgres, Redis, or Kafka. Worker checks imported the entry module and did not call `main` / `run`.

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

Both `services/core/api-gateway/app/core/config.py` and `services/core/auth-service/app/core/config.py` require `jwt_secret` (`JWT_SECRET`). The lab `.env` files set `dev-secret-change-in-production`. Algorithm is the literal `HS256` in `api-gateway/app/dependencies.py` (`jwt.decode`) and `auth-service/app/services/auth_service.py` (`jwt.encode` / `jwt.decode`). No issuer or audience. Access-token claims are `sub` (username), `role`, `exp`. Lifetime is `token_expire_minutes`, default 30 (`TOKEN_EXPIRE_MINUTES`). Gateway 401 bodies: `Missing authorization header`, `Token expired`, `Invalid token: {exc}`. Auth login 401 body is `Invalid credentials` for an unknown user and for a bad password. Auth decode 401 bodies match the gateway (`Token expired`, `Invalid token: {exc}`).

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
| `telemetry.py` | `setup_telemetry` / `setup_worker_telemetry` build a `TracerProvider`, `BatchSpanProcessor`, and OTLP gRPC exporter. FastAPI setup also calls `FastAPIInstrumentor.instrument_app`. An empty `otlp_endpoint` skips the exporter and still installs the client instrumentors. |
| `sentry_setup.py` | Empty `dsn` returns before `sentry_sdk.init`. `traces_sample_rate=0.1` when a DSN is set. |
| `logging.py` | `setup_logging` configures structlog JSON on stdout. No Datadog fields. |
| `redis_cache.py` | `start_redis` sets `app.state.redis`. Cache get/set/delete swallow errors and log a warning. |
| `models/` | `User` table `users` (`id`, `username` unique, `hashed_password`, `role` default `user`). `Task` table `tasks` (`id` UUID, `title`, `status` enum `taskstatus`: `created`, `in_progress`, `completed`, `created_at`, `updated_at`). Indexes `ix_tasks_status`, `ix_tasks_created_at`. |

Base Dockerfiles run uvicorn or `python -m`. Datadog (`ddtrace`, `docker-compose.datadog.yml`, `ddtrace-run`) is removed.

## migrations (`migrations/`)

`alembic.ini` has no `sqlalchemy.url`. `script_location = alembic` is relative to the cwd (the image `WORKDIR` is `/app`). `alembic/env.py` builds `postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}`. `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, and `POSTGRES_HOST` are required. `POSTGRES_PORT` defaults to `5432`. It does not read `DATABASE_URL`. Online mode uses an async engine and `pool.NullPool`. Compose service `migrations` runs `alembic upgrade head` once (`restart: "no"`) after postgres is healthy. Head is `0002`. No seed in the revisions.

## Connection settings (env vs code default)

"Required" means `Settings()` raises if the variable is missing. Connection hosts have no code default. Ports that are not hosts still default (`POSTGRES_PORT` 5432, `SMTP_PORT` 11025). None of these are read from a single `DATABASE_URL` inside the services (only `scripts/seed_dev.py` uses `DATABASE_URL`). Lab values live in each service `.env` / `.env.example`.

| Setting | api-gateway | auth-service | task-service | webhook-receiver | dispatcher | notification-worker | scheduler-worker |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Postgres | none | required `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`; port default 5432. DSN `postgresql+asyncpg` | same shape, all four required, no `service_name` default | none | none | none | same four required; DSN `postgresql+psycopg2`; port default 5432 |
| Redis | none | `REDIS_URL` required (lab DB index 1) | `REDIS_URL` required (lab DB index 0) | none | none | none | `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` required (lab DB index 2) |
| Kafka | none | none | `KAFKA_BOOTSTRAP_SERVERS` required | required | required | required | required |
| `WEBHOOK_URL` | none | none | none | none | required | none | required |
| `JWT_SECRET` | required | required | none | none | none | none | none |
| SMTP host | none | none | none | none | none | `SMTP_HOST` required, port default `11025` | none |

Also required, no host default: gateway `AUTH_SERVICE_URL`, `INTEGRATION_SERVICE_URL`, `TASK_SERVICE_URL`; simulator `INTEGRATION_SERVICE_WEBHOOK_URL`. Alembic requires `POSTGRES_HOST` (`POSTGRES_PORT` still defaults to `5432`). Every FastAPI service, webhook-dispatcher, and both workers still default `OTLP_ENDPOINT` to `http://otel-collector:4317` (tests set it empty; not a connection seam).

## Hard-coded timings

| What | Where | Value | Env? |
| --- | --- | --- | --- |
| Gateway HTTP timeout | `api-gateway` `gateway_timeout` | 5.0 s | `GATEWAY_TIMEOUT` |
| Access-token TTL | auth `token_expire_minutes` | 30 min | `TOKEN_EXPIRE_MINUTES` |
| User cache | auth `auth_service._USER_CACHE_TTL`, key `user:{username}` | 300 s | no |
| Task list / item cache | task `TaskService` | 60 s key `tasks:list`; 120 s key `tasks:{id}` | no |
| Dispatcher attempts | `max_retries` | 3 | `MAX_RETRIES` |
| Dispatcher backoff | `webhook_backoff_base` | after attempt `n` (when `n < max_retries`): sleep `base * 2^(n-1)` seconds plus `random.uniform(0, backoff * 0.1)` (zero to +10%, not ±10%). Default base 1.0, so 3 attempts sleep ~1 s then ~2 s. No 4 s sleep unless `MAX_RETRIES` ≥ 4 | `WEBHOOK_BACKOFF_BASE` (jitter cap stays 10%) |
| Dispatcher HTTP timeout | `webhook_timeout` | 10 s | `WEBHOOK_TIMEOUT` |
| Simulator inbound POST | `routes._send_with_retry` | timeout 10 s; sleep `delay * 2**attempt` between tries. Query `delay` default 1.0, `retry` default 0 | no |
| Beat | `scheduler` `celery.py` `beat_schedule` | `retry_failed_webhooks` every 60.0 s; `cleanup_old_tasks` every 300.0 s | `DLQ_REPLAY_INTERVAL_SECONDS`, `CLEANUP_INTERVAL_SECONDS` |
| DLQ drain caps | `webhook_retry_service` | 200 messages, 20 s wall, consumer `consumer_timeout_ms=5000` | no |
| Celery DLQ HTTP retry | `retry_single_webhook` | `autoretry_for=(httpx.RequestError,)`, `max_retries=5`, `retry_backoff=True`, `retry_backoff_max=300`, `acks_late=True`. Any `HTTPStatusError` (4xx and 5xx) is permanent | no |
| Cleanup age | `cleanup_completed_tasks_minutes` | 5 minutes. `0` disables. Column compare is `updated_at < now - minutes`. Not hours | `CLEANUP_COMPLETED_TASKS_MINUTES` |
| Cleanup Celery retry | `cleanup_tasks.py` | `max_retries=3`, `default_retry_delay=60` | no |
| Metrics port | dispatcher, notification, scheduler | 9100 | `METRICS_PORT` |

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
| mailhog | `wget` `http://127.0.0.1:8025/api/v2/messages` | HTTP API |
| postgres-exporter, kafka-exporter | `wget` `/metrics` on 9187 and 9308 | process metrics |
| frontend | `node` fetch `http://127.0.0.1:5173/` | Vite dev server on the default image stage |

`infra/test-stack.services` is the explicit test stack (no exporters). `infra/docker-compose.test.yml` selects the frontend `preview` image stage (`vite build` then `vite preview` on port 5173). Toxiproxy has no shell or HTTP client in the image, so it has no healthcheck.

`ASGITransport` does not run `on_event`, so a test that needs Redis or Kafka must enter the app lifespan itself. `get_db` closes over the module-level `SessionLocal` built from the environment at import.

## Hazards

- nginx limits by the `Authorization` value. One shared bearer token is one `20r/s` bucket on `location /`. `/auth/token` carries no `Authorization` header, so its key is empty and nginx does not account it: the `5r/m` limit is probably inactive (BUG-1 candidate, confirm in P6.2). `/auth/me` is not limited. `/webhooks/` is `20r/s` burst 20 `nodelay`, not the `location /` burst of 100.
- `GET /ready` stays 200 when Redis, Kafka, or Postgres is down. Compose treats that as healthy for the FastAPI services.
- Importing any FastAPI `app.main` starts `OtelBatchSpanRecordProcessor` and it tries `OTLP_ENDPOINT` (`http://otel-collector:4317` if unset). The scratch run logged `StatusCode.UNAVAILABLE` for that DNS name after `/openapi.json`.
- Every service package is named `app`. Two services cannot be imported in one process. `prometheus_metrics` registers global collectors at import. Scheduler import sets `PROMETHEUS_MULTIPROC_DIR` and creates that directory.
- `requirements.txt` does not pin SQLAlchemy and does not list the OTEL SDK. This venv resolved SQLAlchemy 2.1.3, and the SQLAlchemy instrumentor then instrumented nothing. Import still succeeded. Images only import because the Dockerfile installs `shared[services]`.
- Gateway OpenAPI has duplicate operation IDs (warning, HTTP 200).
- Dispatcher backoff is `1 * 2^(attempt-1)` plus 0..10% and, with the default 3 attempts, waits twice (~1 s, ~2 s). Scheduler DLQ replay does not send `Idempotency-Key`, and it treats 5xx as final. Notification SMTP failures are swallowed. `tenacity` is unused.
- User cache stores `hashed_password` for 300 s. Task cache returns dicts on hit and ORM rows on miss.
- `scripts/seed_dev.py` is not run by compose. Postgres is not published, so the script's default `localhost:5432` does not match this compose file.
- Alembic `script_location` is relative to the cwd. Running it outside `migrations/` fails with `Path doesn't exist: alembic` before it connects.
