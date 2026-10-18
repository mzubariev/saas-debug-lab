# System Architecture

SaaS Debug Lab is a task-board backend: synchronous HTTP through nginx and api-gateway, and asynchronous task events on Kafka in KRaft combined mode. Service images are `python:3.11-slim`. Facts below follow `testing/docs/human/SUT_MAP_FULL.md`, `infra/docker-compose.yml`, and `testing/KNOWN_ISSUES.md`.

## Compose profiles


| Profile         | What it starts                                                                                                                                                                                                                                               |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `core`          | nginx, api-gateway, auth-service, task-service, webhook-receiver, webhook-dispatcher, external-service-simulator, notification-worker, scheduler-worker, frontend, migrations, Postgres, postgres-exporter, Redis, Kafka, kafka-exporter, MailHog, Toxiproxy |
| `observability` | Jaeger, OpenTelemetry Collector, Prometheus, Grafana, Fluent Bit, Elasticsearch, Kibana                                                                                                                                                                      |




## Lab URL templates

Compose `env_file` is each service `.env`. Those files are gitignored. The tracked lab values are the `.env.example` siblings. `.github/actions/test-stack/action.yml` copies every `*.env.example` outside `testing/` onto `.env`.


| Setting                           | Lab template                                                                                | Value                                   |
| --------------------------------- | ------------------------------------------------------------------------------------------- | --------------------------------------- |
| `AUTH_SERVICE_URL`                | `services/core/api-gateway/.env.example`                                                    | `http://auth-service:8000`              |
| `TASK_SERVICE_URL`                | `services/core/api-gateway/.env.example`                                                    | `http://task-service:8000`              |
| `INTEGRATION_SERVICE_URL`         | `services/core/api-gateway/.env.example`                                                    | `http://webhook-receiver:8000`          |
| `WEBHOOK_URL`                     | `services/core/webhook-dispatcher/.env.example` and `workers/scheduler-worker/.env.example` | `http://nginx/external/receive-webhook` |
| `INTEGRATION_SERVICE_WEBHOOK_URL` | `services/external/external-service-simulator/.env.example`                                 | `http://localhost/webhooks/inbound`     |


The test overlay keeps the three gateway URLs. It sets both `WEBHOOK_URL` values to `http://wiremock:8080/external/receive-webhook` and the simulator URL to `http://api-gateway:8000/webhooks/inbound`. The simulator example also sets `DEFAULT_FAIL_RATE=0.0`, `DEFAULT_DELAY=0.0`, and `DEFAULT_STATUS=200`. `http://nginx/external/receive-webhook` hits nginx, which strips `/external/` and proxies to the simulator. `http://localhost/webhooks/inbound` inside the simulator container is the simulator itself.

## Lifespan

FastAPI apps use a lifespan. Import still calls logging, Sentry, and telemetry setup. `httpx.ASGITransport` does not run the lifespan, so a caller that needs Redis or Kafka has to enter it.


| Process                    | Startup                                                                                                                                                                  | Shutdown                                   |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------ |
| api-gateway                | `httpx.AsyncClient(timeout=gateway_timeout)` on `app.state.http_client`                                                                                                  | close that client                          |
| auth-service               | `start_redis` (`app.state.redis`). Async engine exists at import and connects on first use                                                                               | stop Redis, then dispose the engine        |
| task-service               | Kafka producer (`app.state.kafka`), then Redis. `AsyncExitStack`: dispose is registered first and runs last                                                              | stop Redis, stop Kafka, dispose the engine |
| webhook-receiver           | Kafka producer (`app.state.kafka_producer`)                                                                                                                              | stop the producer                          |
| external-service-simulator | no startup handler                                                                                                                                                       | none                                       |
| webhook-dispatcher         | no FastAPI app. `main()` starts logging, worker telemetry, Sentry, `start_http_server`, then the producer, `httpx.AsyncClient`, and consumer                             | process exit                               |
| notification-worker        | `run()` starts telemetry, Sentry, and the metrics server, then `consume()`                                                                                               | process exit                               |
| scheduler-worker           | Celery import sets `PROMETHEUS_MULTIPROC_DIR` and instruments Celery. Telemetry, Sentry, SQLAlchemy instrumentation, and the metrics server run in `worker_process_init` | process exit                               |


`GET /health` returns `{"status":"ok"}` and `GET /ready` returns `{"status":"ready"}`. Both are static. Compose healthchecks call `/health`. A down Postgres, Redis, or Kafka still leaves `/ready` at 200, and Compose treats the FastAPI services as healthy.

Every Python service package is named `app`, so two services cannot be imported in one process.

## nginx

Host `80:80`, image `nginx:1.25-alpine`, config `infra/nginx/nginx.conf`. Upstream `api-gateway:8000` with keepalive 32. api-gateway `8000` is not published. `proxy_connect_timeout 5s`, `proxy_send_timeout 10s`, `proxy_read_timeout 30s`. Buffering is on: `proxy_buffer_size 16k`, `proxy_buffers 4 16k`, `proxy_busy_buffers_size 32k`. Forwarded headers: `Host` (`$http_host`), `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`. `limit_req_status 429`. `limit_req_log_level warn`. Access logs are JSON (`json_combined`) on stdout.

Zone `api` is `10m` at `20r/s`, keyed by `$limit_key`. That map uses `$http_authorization`, and `$binary_remote_addr` when the header is empty, so each client IP has its own bucket on `/`, `/webhooks/`, and `/otel/`. Zone `auth` is `10m` at `5r/m`, keyed by `$http_authorization`. An empty auth key is not counted.


| Zone   | Rate    | Location                       | Burst                                                                         |
| ------ | ------- | ------------------------------ | ----------------------------------------------------------------------------- |
| `api`  | `20r/s` | `location /`                   | `burst=100` (excess is delayed)                                               |
| `api`  | `20r/s` | `location /webhooks/`          | `burst=20 nodelay`                                                            |
| `api`  | `20r/s` | `location /otel/`              | `burst=20 nodelay`, `client_max_body_size 1m`, proxy to `otel-collector:4318` |
| `auth` | `5r/m`  | `location /auth/token`         | `burst=3 nodelay`                                                             |
| none   |         | `location /auth/` (`/auth/me`) | no `limit_req`                                                                |
| none   |         | `location /external/`          | proxy to `external-service-simulator:8000/`, prefix stripped                  |


`POST /auth/token` carries no `Authorization` header, so the auth zone does not count it (BUG-1). `/` and `/webhooks/` are separate locations; the longer prefix wins.

## api-gateway

Directory `services/core/api-gateway`. Entrypoint `app.main:app` on container port 8000. The lifespan client is the only HTTP client: proxy routes take it through `get_http_client`. Timeout is `gateway_timeout` (default 5.0 s, `GATEWAY_TIMEOUT`). Downstream timeout becomes 504 `Downstream timeout`. Other `httpx.RequestError` becomes 502 `Downstream unavailable`. Upstream status and body pass through.

`CORS_ORIGINS` defaults to empty. The lab allows `http://localhost:5173`, `http://127.0.0.1:5173`, and `http://localhost`.

Gateway proxy routes (no response models; each method has its own operationId):


| Methods                     | Gateway path              | Upstream                  | Gateway auth                                      |
| --------------------------- | ------------------------- | ------------------------- | ------------------------------------------------- |
| `GET POST PUT DELETE`       | `/auth/{path}`            | `AUTH_SERVICE_URL`        | none                                              |
| `GET POST PUT PATCH DELETE` | `/tasks`, `/tasks/{path}` | `TASK_SERVICE_URL`        | `verify_token` (`HTTPBearer`, `auto_error=False`) |
| `GET POST PUT PATCH DELETE` | `/webhooks/{path}`        | `INTEGRATION_SERVICE_URL` | none                                              |


`AUTH_SERVICE_URL`, `TASK_SERVICE_URL`, and `INTEGRATION_SERVICE_URL` are required and have no code default. Lab and test values are in [Lab URL templates](#lab-url-templates).

The proxy drops `host`, `sentry-trace`, `baggage`, `traceparent`, and `tracestate`. JWT check is local: algorithm `HS256`, secret `JWT_SECRET`, no issuer or audience. 401 bodies: `Missing authorization header`, `Token expired`, `Invalid token: {exc}`.

Compose healthcheck uses Python `urllib` because this image has no curl. Memory limit `512m`.

## auth-service

Directory `services/core/auth-service`. Async SQLAlchemy and asyncpg. The engine object is created at import. Passwords use passlib argon2. A NUL byte in the username is 422 before the query.


| Method | Path          | Body                        | Response                                      | Auth                          |
| ------ | ------------- | --------------------------- | --------------------------------------------- | ----------------------------- |
| POST   | `/auth/token` | form `username`, `password` | `access_token`, `token_type` default `bearer` | none                          |
| GET    | `/auth/me`    | Bearer                      | `username`, `role`                            | decode only; no database read |


Login 401 body is `Invalid credentials` for an unknown user and for a bad password. Access-token claims are `sub` (username), `role`, and `exp`. Lifetime is `token_expire_minutes`, default 30 (`TOKEN_EXPIRE_MINUTES`).

`users` columns: `id`, `username` (unique), `hashed_password`, `role` default `user`. Redis is required (`REDIS_URL`, lab DB index 1). After a successful password check the service writes `user:{username}` for 300 s with `username`, `hashed_password`, and `role` (BUG-4b). A wrong password leaves no key. Cache errors are swallowed. Migrations do not insert users. `scripts/seed_dev.py` is manual: `admin` / `admin123` role `admin`, `user` / `user123` role `user`.

Compose healthcheck: `curl` `http://localhost:8000/health`. Memory limit `512m`.

## task-service

Directory `services/core/task-service`. Same async engine-at-import pattern. This service does not check JWTs. Routes: `GET /tasks`, `POST /tasks` (201), `GET /tasks/{task_id}`, `PATCH /tasks/{task_id}/start`, `PATCH /tasks/{task_id}/complete`.

`TaskCreate.title` is `min_length=1`, `max_length=255`. An empty title, a title longer than 255, a NUL byte, and a lone surrogate are 422. Migration `0002` leaves `tasks.title` unbounded (`sa.String()` with no length).

`tasks` columns: `id` UUID, `title`, `status`, `created_at`, `updated_at`. Status enum `taskstatus`: `created`, `in_progress`, `completed`. Indexes `ix_tasks_status`, `ix_tasks_created_at`. `start` is allowed only from `created`. `complete` is allowed only from `in_progress`. Anything else is 409. A missing row is 404 `Task not found`.

`GET /tasks` returns every row (`list_all`). There is no limit or offset. List cache key `tasks:list` lives 60 s. Item key `tasks:{id}` lives 120 s. A hit returns the stored dict; a miss returns the ORM row. `response_model` is `TaskOut` either way. Redis lab DB index is 0. Cache errors are swallowed.

The repository commits, then the service publishes, then it deletes the list key (and the item key on a transition). Postgres, Redis, and `KAFKA_BOOTSTRAP_SERVERS` are required. Memory limit `512m`.

## webhook-receiver

Directory `services/core/webhook-receiver`. No database and no Redis. `POST /webhooks/inbound` takes `event` (string) and `data` (object, default `{}`) and returns 200 `{"status":"received","event": ...}`. No auth. The producer writes topic `TOPIC_WEBHOOK_INBOUND` (default `webhook_inbound`). A publish failure is logged and re-raised. Memory limit `256m`.

## webhook-dispatcher

Directory `services/core/webhook-dispatcher`. Entry `python -m app.run`. No compose healthcheck and no published port in the lab file. Metrics listen on `METRICS_PORT` (compose sets `9100`) once `main()` has started the server.

Consumer: `task_created` and `task_updated` (`CONSUME_TOPICS`, not an env var), group `webhook-dispatcher`, `auto_offset_reset=earliest`. Each POST sends `Idempotency-Key: str(payload.id)`. `WEBHOOK_URL` is required and has no code default. The lab template and the test overlay value are in [Lab URL templates](#lab-url-templates).

4xx stops and writes `webhook_dlq`. 5xx and `httpx.RequestError` retry, then the DLQ. Produce errors are logged and swallowed. Memory limit `256m`. Depends on Kafka and external-service-simulator healthy.

## external-service-simulator

Directory `services/external/external-service-simulator`. No database, Redis, or Kafka. Lab publishes `8000:8000`. Idempotency state is an in-memory set in the process. `INTEGRATION_SERVICE_WEBHOOK_URL` is required. The lab template and the test overlay value are in [Lab URL templates](#lab-url-templates).


| Method | Path               | Behaviour                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ------ | ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| POST   | `/receive-webhook` | Query `fail_rate` 0..1, `delay` ≥ 0, `status` int. A stored `Idempotency-Key` returns 200 `{"status":"duplicate",...}` before the delay. Otherwise sleep `delay`, then `fail_rate` → 500 `simulated_failure` (key not stored), or a non-200 `status` → that code (key not stored), or 200 `{"status":"received","payload":...}` and the key is stored. Settings defaults: fail 0.0, delay 0.0, status 200. Compose maps `DEFAULT_FAIL_RATE` from `EXTERNAL_SIMULATOR_DEFAULT_FAIL_RATE` (default `0.0`). |
| POST   | `/trigger-event`   | Body `event`, `data` default `{}`. Query `retry` default 0, `delay` default 1.0. Returns 202 immediately. A background POST goes to `INTEGRATION_SERVICE_WEBHOOK_URL` (timeout 10 s, sleep `delay * 2**attempt` between tries).                                                                                                                                                                                                                                                                          |


Memory limit `256m`. No `depends_on`.

## Workers



### notification-worker

Directory `workers/notification-worker`. Entry `python -m app.worker`. Group `notification-worker`, topic `task_created` only, `auto_offset_reset=earliest`. SMTP via `aiosmtplib` to `SMTP_HOST` / `SMTP_PORT`. `SMTP_HOST` has no code default; Compose sets `${SMTP_HOST:-toxiproxy}`. Port default `11025` (`SMTP_PORT`). `SMTP_USE_TLS` and `SMTP_USE_STARTTLS` default false. From / to default `notifications@saas-debug-lab.local` and `change-me@emailhook.site`. MIME alternative, plain plus HTML. `SMTPException` and `OSError` are counted and logged, and the consumer continues. No email retry. No compose healthcheck. Depends on Kafka only. Metrics port 9100 inside `run()`. Memory limit `256m`.

This worker and webhook-dispatcher use different groups, so each receives every `task_created` record.

### scheduler-worker

Directory `workers/scheduler-worker`. Command: `celery -A app.core.celery:celery_app worker --beat --loglevel=info --concurrency=2 --prefetch-multiplier=1`. Broker and result backend are required (`CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`; lab Redis DB index 2). Sync SQLAlchemy and psycopg2, engine created on first use, `pool_pre_ping=True`. No compose healthcheck. Depends on Redis, Postgres, Kafka, and migrations completed. Memory limit `384m`.

`PROMETHEUS_MULTIPROC_DIR` is `/tmp/prometheus_multiproc_scheduler`. With that directory set, only the child that takes `metrics_http.lock` binds `METRICS_PORT`. The beat parent does not bind it.


| Job                     | Schedule env                  | Default | Work                                                                                                                                                                                                                                                                |
| ----------------------- | ----------------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `retry_failed_webhooks` | `DLQ_REPLAY_INTERVAL_SECONDS` | 60 s    | Drain `webhook_dlq`, group `scheduler-worker`, `enable_auto_commit=True`, `auto_offset_reset=earliest`. Each message is `retry_single_webhook.delay(...)` after the `error` field is dropped. `attempts` and `timestamp` stay. The POST sends no `Idempotency-Key`. |
| `cleanup_old_tasks`     | `CLEANUP_INTERVAL_SECONDS`    | 300 s   | `DELETE FROM tasks WHERE status = 'completed' AND updated_at < :cutoff`. Age is `CLEANUP_COMPLETED_TASKS_MINUTES`, default 5. `0` disables the delete.                                                                                                              |


`retry_single_webhook` retries `httpx.RequestError` only (`max_retries=5`, `retry_backoff=True`, `retry_backoff_max=300`, `acks_late=True`). Any `HTTPStatusError`, 4xx or 5xx, is permanent (BUG-12). `WEBHOOK_URL` is required, has no code default, and uses the same lab template as webhook-dispatcher.

## Frontend

Directory `frontend/`. Lab publishes `5173:5173` and sets `VITE_API_URL=http://localhost`. The default image stage is the Vite dev server. The test overlay builds the `preview` stage (`vite build`, then `vite preview` on container port 5173) and publishes host `5174`. Compose can pass `VITE_SENTRY_DSN` and `VITE_SENTRY_TRACES_SAMPLE_RATE` (default `1.0`). The login error element has `role="alert"`.

## Postgres, Redis, Kafka



### Postgres

Image `postgres:15` (major 15, tag not minor-pinned). No host port in the lab file. Command sets `shared_preload_libraries=pg_stat_statements`, `pg_stat_statements.track=all`, `pg_stat_statements.max=10000`. First init runs `infra/postgres/init.sql`. Volume `postgres_data`.

`migrations/` is the only Alembic tree. Head is `0002`. No seed in the revisions. Compose service `migrations` runs `alembic upgrade head` once (`restart: "no"`) after Postgres is healthy. `alembic/env.py` builds `postgresql+asyncpg://...` from `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, and `POSTGRES_HOST` (all required). `POSTGRES_PORT` defaults to `5432`. It does not read `DATABASE_URL`. `script_location` is relative to the cwd; the image `WORKDIR` is `/app`.

`scripts/seed_dev.py` reads `DATABASE_URL`, default `postgresql://admin:admin@localhost:5432/saas`. The lab compose file does not publish `5432`, so that default does not reach this Postgres. The script uses psycopg (v3) and inserts users with `ON CONFLICT (username) DO NOTHING`, plus ten tasks with UUIDs `11111111-0000-0000-0000-000000000001` through `...0010`.

postgres-exporter image `prometheuscommunity/postgres-exporter:latest`. Healthcheck reads `:9187/metrics`. Queries file `observability/postgres-exporter/queries.yaml`.

### Redis

Image `redis:7`. No host port in the lab file. Volume `redis_data`. Cache helpers in `saas_shared.redis_cache` log a warning and continue when Redis errors.


| Consumer         | Lab URL shape                                               |
| ---------------- | ----------------------------------------------------------- |
| task-service     | `REDIS_URL`, DB index 0                                     |
| auth-service     | `REDIS_URL`, DB index 1                                     |
| scheduler-worker | `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND`, DB index 2 |




### Kafka

Image `confluentinc/cp-kafka:7.5.0`. `KAFKA_PROCESS_ROLES=broker,controller`. Node id 1, controller quorum `1@kafka:9094`, log dir `/tmp/kraft-combined-logs`. Replication factor 1 for offsets and the transaction state log. No host port in the lab file.


| Listener         | Bind           | Advertised                          |
| ---------------- | -------------- | ----------------------------------- |
| `PLAINTEXT`      | `kafka:9092`   | `kafka:9092`                        |
| `CONTROLLER`     | `kafka:9094`   | not in `KAFKA_ADVERTISED_LISTENERS` |
| `PLAINTEXT_HOST` | `0.0.0.0:9093` | `localhost:9093`                    |


Healthcheck: `kafka-topics --bootstrap-server kafka:9092 --list`, `start_period` 30s. kafka-exporter image `danielqsj/kafka-exporter:latest`, listen `:9308`.

#### Envelope

`shared/saas_shared/kafka_envelope.py`. `build_envelope` / `encode_envelope_bytes` write:


| Field        | Value                                                               |
| ------------ | ------------------------------------------------------------------- |
| `event_type` | `task.created`, `task.updated`, `webhook.inbound`, or `webhook.dlq` |
| `version`    | `v1`                                                                |
| `trace_id`   | the argument, otherwise `uuid4().hex`                               |
| `timestamp`  | UTC ISO                                                             |
| `payload`    | business object                                                     |


`parse_envelope_message` returns `(event_type, payload, trace_id)` for a v1 object whose `payload` is a dict. Any other dict becomes `("unknown", that_dict, None)`. Invalid JSON, non-dict JSON, non-UTF-8 bytes, and other types become `("unknown", {}, None)`.

Task payload fields are `id`, `title`, `status`. Inbound payload is `event`, `data`. DLQ payload is the business payload plus `error`, `attempts`, `timestamp`. Producers also set W3C headers via `otel_kafka_headers` in `saas_shared.kafka_trace`. `saas_shared.kafka_messaging` builds the semantic Kafka spans. task-service also sets `sentry-trace` and `baggage`.

Topic names, producers, and consumer groups are in the [service map](./SERVICE_MAP.md).

## Timings


| What                      | Where                                         | Value                                                                                                                                                                                      | Env                               |
| ------------------------- | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------- |
| Gateway HTTP timeout      | api-gateway `gateway_timeout`                 | 5.0 s                                                                                                                                                                                      | `GATEWAY_TIMEOUT`                 |
| Access-token TTL          | auth `token_expire_minutes`                   | 30 min                                                                                                                                                                                     | `TOKEN_EXPIRE_MINUTES`            |
| User cache                | auth `_USER_CACHE_TTL`, key `user:{username}` | 300 s                                                                                                                                                                                      | none                              |
| Task list cache           | task `TaskService`                            | 60 s, key `tasks:list`                                                                                                                                                                     | none                              |
| Task item cache           | task `TaskService`                            | 120 s, key `tasks:{id}`                                                                                                                                                                    | none                              |
| Dispatcher attempts       | `max_retries`                                 | 3                                                                                                                                                                                          | `MAX_RETRIES`                     |
| Dispatcher backoff        | `webhook_backoff_base`                        | after attempt `n` while `n < max_retries`: `base * 2^(n-1)` seconds plus `random.uniform(0, backoff * 0.1)` (0% to +10%). Default base 1.0, so the two sleeps are about 1 s then about 2 s | `WEBHOOK_BACKOFF_BASE`            |
| Dispatcher HTTP timeout   | `webhook_timeout`                             | 10 s                                                                                                                                                                                       | `WEBHOOK_TIMEOUT`                 |
| Simulator background POST | `routes._send_with_retry`                     | timeout 10 s; sleep `delay * 2**attempt`. Query `delay` default 1.0, `retry` default 0                                                                                                     | none                              |
| Beat DLQ replay           | scheduler `beat_schedule`                     | every 60.0 s                                                                                                                                                                               | `DLQ_REPLAY_INTERVAL_SECONDS`     |
| Beat cleanup              | scheduler `beat_schedule`                     | every 300.0 s                                                                                                                                                                              | `CLEANUP_INTERVAL_SECONDS`        |
| DLQ drain caps            | `webhook_retry_service`                       | 200 messages, 20 s wall, `consumer_timeout_ms=5000`                                                                                                                                        | none                              |
| Celery DLQ HTTP retry     | `retry_single_webhook`                        | `httpx.RequestError` only, `max_retries=5`, `retry_backoff=True`, `retry_backoff_max=300`, `acks_late=True`. Any `HTTPStatusError` is one POST                                             | none                              |
| Cleanup age               | `cleanup_completed_tasks_minutes`             | 5 minutes. `0` disables. Compare `updated_at < now - minutes`                                                                                                                              | `CLEANUP_COMPLETED_TASKS_MINUTES` |
| Cleanup Celery retry      | `cleanup_tasks.py`                            | `max_retries=3`, `default_retry_delay=60`                                                                                                                                                  | none                              |
| Worker metrics port       | dispatcher, notification, scheduler           | 9100                                                                                                                                                                                       | `METRICS_PORT`                    |


The cleanup age and the beat interval are separate settings. Both defaults are five minutes of wall time; one is the row age, the other is how often the job runs.

## Trust boundary

Host HTTP enters through nginx `:80`, except the ports the [service map](./SERVICE_MAP.md) publishes (simulator, frontend, MailHog UI, Toxiproxy admin). The gateway verifies a Bearer token only for `/tasks` and `/tasks/{path}`. `/auth/*` and `/webhooks/*` are proxied with no gateway check. task-service does not verify the token. Services share the Compose network and treat that network as trusted.

The `role` claim is written at login and copied by `verify_token` and `GET /auth/me`. No route checks it.

## Known design limits

Detail and status live in [testing/KNOWN_ISSUES.md](../../testing/KNOWN_ISSUES.md).


| Limit            | Behaviour                                                                                                                                                                                                                     |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| BUG-1            | `location /auth/token` is zone `auth` at `5r/m` burst 3, keyed by `$http_authorization`. Logins send no `Authorization` header. An empty zone key is not counted, so the limit does not apply. `/auth/me` has no `limit_req`. |
| BUG-3            | task-service commits, then publishes. A Kafka failure returns 500, the row stays (a create stays stored, a start stays `in_progress`), the event is not published, and the cache delete does not run.                         |
| BUG-7            | webhook-dispatcher sets `Idempotency-Key` from `payload.id`. `task_created` and both `task_updated` deliveries for one task share that key.                                                                                   |
| BUG-12           | scheduler `retry_single_webhook` treats every `HTTPStatusError` as final. A 5xx is one POST.                                                                                                                                  |
| No authZ         | `role` is on the token and on `GET /auth/me`. No route authorizes with it.                                                                                                                                                    |
| `GET /tasks`     | Returns every row. No limit or offset. Pagination is client-side.                                                                                                                                                             |
| Static readiness | `/health` and `/ready` do not ping Postgres, Redis, or Kafka. Compose uses `/health` as the FastAPI healthcheck.                                                                                                              |
| BUG-4b           | `user:{username}` stores `hashed_password` for 300 s after a successful login.                                                                                                                                                |




## Observability

Lab apps default `OTLP_ENDPOINT` to `http://otel-collector:4317`. An empty endpoint skips the OTLP exporter and still installs the client instrumentors. `setup_telemetry` / `setup_worker_telemetry` build a `TracerProvider`, `BatchSpanProcessor`, and an OTLP gRPC exporter. FastAPI setup also calls `FastAPIInstrumentor.instrument_app`. Sentry `traces_sample_rate` is `0.1` when `SENTRY_DSN` is set. An empty DSN returns before `sentry_sdk.init`.


| Piece          | Image                                                  | Lab publish   | Role                                                                                                                                                      |
| -------------- | ------------------------------------------------------ | ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Jaeger         | `jaegertracing/all-in-one:1.55`                        | `16686:16686` | UI. `COLLECTOR_OTLP_ENABLED=true`                                                                                                                         |
| otel-collector | `otel/opentelemetry-collector:0.96.0`                  | none          | Config `observability/otel-collector/otel-collector-config.yaml`. Compose describes it as OTLP to Jaeger. nginx `/otel/` proxies to `otel-collector:4318` |
| Prometheus     | `prom/prometheus`                                      | `9090:9090`   | Config `observability/prometheus/prometheus.yml` and `observability/prometheus/rules/`. Command enables `exemplar-storage`                                |
| Grafana        | `grafana/grafana`                                      | `3000:3000`   | Provisioning `observability/grafana/provisioning/`                                                                                                        |
| Fluent Bit     | `fluent/fluent-bit:3.0`                                | none          | Reads Docker container logs. Config under `observability/fluent-bit/`                                                                                     |
| Elasticsearch  | `docker.elastic.co/elasticsearch/elasticsearch:8.11.0` | none          | Container port 9200 (`http://elasticsearch:9200`). Single-node, `xpack.security.enabled=false`, heap `-Xms512m -Xmx512m`                                  |
| Kibana         | `docker.elastic.co/kibana/kibana:8.11.0`               | `5601:5601`   | Depends on Elasticsearch                                                                                                                                  |


`GET /metrics` on FastAPI apps is `include_in_schema=False`. OpenMetrics is used when `Accept` contains `application/openmetrics-text`; otherwise the body is Prometheus text. The HTTP middleware replaces UUID and integer path segments with `{id}`, strips a trailing slash, and skips `/metrics`. Import of `prometheus_metrics` registers global collectors and sets `machine_cpu_cores` and `container_memory_limit_bytes` (`0` when cgroup files are absent).

structlog writes JSON to stdout. `setup_logging` is what each process calls.

## MailHog and Toxiproxy

MailHog image `mailhog/mailhog:latest`. Web UI `8025:8025`. Healthcheck: `wget` `http://127.0.0.1:8025/api/v2/messages`. SMTP port 1025 is not published; notification-worker reaches SMTP through Toxiproxy.

Toxiproxy image `ghcr.io/shopify/toxiproxy:latest`. Management API `8474:8474`. Command `-config /etc/toxiproxy.json -host 0.0.0.0`, file `infra/toxiproxy/toxiproxy.json`. Depends on MailHog `service_started`. The image has no shell or HTTP client, so Compose defines no healthcheck. Compose does not publish `11025`; that value is the worker `SMTP_PORT` default, aimed at the `toxiproxy` hostname.