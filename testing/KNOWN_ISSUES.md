# Known issues

## Defects

### Confirmed

- BUG-2: task-service `TaskCreate.title` is an unconstrained string. `POST /tasks` stores an empty title and a 10000-character title and returns 201. Expected 422. `xfail(strict=True)` on those two cases. A non-string title does return 422.
- BUG-3: task-service commits in the repository, then calls `publish_event`. A Kafka failure returns 500, the task row remains (a create stays stored, a start stays `in_progress`), the event is not published, and `cache_delete` does not run. `xfail(strict=True)` on create and start.
- BUG-4: auth-service login writes `hashed_password` to Redis (`user:{username}`, TTL 300 s) before it checks the password. `xfail(strict=True)` expects that cache entry to omit the hash. A second login reads the cached row.
- BUG-5: webhook-receiver `receive_inbound` logs `event=<payload event>` after a successful publish, and the failure log does the same. structlog already takes that name as the message, so the call raises `TypeError` and the route returns 500 instead of 200. The Kafka message is published before the success log. `xfail(strict=True)` on the 200 response.

### Candidates to confirm

Confirm in the layer that can observe the behaviour, then assign a BUG-n and `xfail(strict=True)`.

- Dispatcher `Idempotency-Key` is `str(payload.get("id", ""))`. `task_created` and `task_updated` for one task both carry that task id, so the two deliveries share one key.
- Scheduler DLQ replay is final on any `httpx.HTTPStatusError` (`autoretry_for` is only `httpx.RequestError`). The DLQ consumer sets `enable_auto_commit=True` and `process_dlq` commits by consuming and closing before the Celery task performs the HTTP call, so a rejected replay is not returned to `webhook_dlq`.
- Dispatcher `_produce` logs `kafka_produce_failed` and does not re-raise. Notification-worker catches `aiosmtplib.SMTPException` and `OSError`, counts them, and does not re-raise.
- The `role` claim is written at login and copied by gateway `verify_token` and `/auth/me`. No route checks it. There is no authZ.
- `GET /tasks` returns every row (`list_all`; no limit or offset).
- nginx `location /auth/token` sets `limit_req zone=auth` (`5r/m`), and the zone key is `$http_authorization`. A login sends no `Authorization` header, so the key is empty and nginx does not account the request. Confirm in P6.2; if it holds, record BUG-1.

## Testability changes

- `infra/docker-compose.datadog.yml`, service `requirements.txt`, `saas_shared.logging`, `saas_shared.sentry_setup`, `saas_shared.telemetry`: removed Datadog (`ddtrace-run`, the `ddtrace` requirement, the log processor, and the Sentry hooks) so a missing package does not stamp `dd_trace_error` on every log line.
- Service and worker `Settings`, plus `migrations/alembic/env.py`: database host, Redis URL (including DB index), Kafka bootstrap, `WEBHOOK_URL`, JWT secret, SMTP host, gateway service URLs, and the simulator webhook URL are required environment variables. A missing variable fails settings load instead of falling back to a Docker DNS name. Lab `.env` files already set the previous values, so compose behaviour is unchanged. `OTLP_ENDPOINT` still defaults to the collector; tests clear it.
- `webhook-dispatcher` `WEBHOOK_BACKOFF_BASE` (default 1.0) and scheduler `DLQ_REPLAY_INTERVAL_SECONDS` (60) / `CLEANUP_INTERVAL_SECONDS` (300). `MAX_RETRIES` and `CLEANUP_COMPLETED_TASKS_MINUTES` (default 5) were already environment settings. Jitter stays 0..10% of the computed backoff.
- Compose healthchecks for mailhog, postgres-exporter, kafka-exporter, and the frontend. FastAPI `/health` checks were already present. `infra/test-stack.services` lists the test stack. `frontend/Dockerfile` `preview` stage runs `vite build` then `vite preview`; the default stage stays `dev`. `infra/docker-compose.test.yml` selects `preview`.

## Decisions since the plan

- P0.1 item 4 skipped: the only import-time side effect the recon found is OpenTelemetry, and tests neutralise it with `OTLP_ENDPOINT=""` and `SENTRY_DSN=""` (no production change). Kafka and Redis already connect in startup.
- Toxiproxy has no in-image shell or HTTP client, so it has no compose healthcheck. Workers stay without one; the test kit checks the metrics port.
- P0.2: each service dependency group also installs `saas-shared[services]` from `../shared`. Image Dockerfiles install that extra and the service `requirements.txt` files do not; in-process imports need it.
- P0.2: `testcontainers` 4.15 has no `postgres` or `kafka` extras (those containers are in the core wheel). The dependency is `testcontainers[redis]`. Service groups use `redis` rather than `redis[asyncio]` because redis 8.1 publishes no `asyncio` extra.
- P0.2: ruff excludes `testing/docs`. Those notes embed Python samples that are not kit code.
- P1: worker database names replace hyphens with underscores (`test_task_service_component_gw0`). The skeleton interpolated the raw service name, which is not the name the definition of done checks for.
- P1: `needs_infra` is true only when `--service` is set or `INFRA=on`, and never for `integration`, `e2e_ui`, `smoke`, or `synthetic`. The skeleton's unit-path and `-m unit` heuristics are not used.
- P1: the template is migrated in `app_template_<head>_building` and renamed into place, so `CREATE DATABASE ... TEMPLATE` does not see an open connection to the source.
- P1: `UserRowFactory` sets `hashed_password` (the `users` column). The skeleton's `password_hash` is not a column. One argon2 hash of `user123` is computed at import.
- P1: pyright `extraPaths` includes `../shared`, and `saas-shared` is a base kit dependency, because row factories import `saas_shared.models`. A service group is no longer required for that import.
- P1: `service_env` sets `SERVICE_NAME` from the selected service. task-service `Settings` requires it and has no default.
- P1: `fastapi` is a base kit dependency. The task-service component conftest imports it, and the lint job runs `uv sync` without a service group.
- P2.6: Redis DB index is the service block plus the worker index. task-service block 0 (databases 0-7) and auth-service block 8 (databases 8-15) do not share an index at `--maxprocesses=8`. An index above 15 raises. Other services stay on block 0; two blocks of 8 fill Redis.
- P2.6: each xdist worker has its own Kafka consumer group (`service-layer-worker-uuid`). `KafkaEventReader` uses `auto_offset_reset=earliest` and waits still keep only the test's own id. The controller pre-creates `task_created`, `task_updated`, `webhook_inbound`, and `webhook_dlq`. The adapter plan used `latest` and did not pre-create topics.
- P2.6: `service_env` applies the catalogue `env` map. Gateway and auth `JWT_SECRET` are `LAB_JWT_SECRET`, the `JwtFactory` default. Scheduler `CELERY_*` uses that worker's Redis URL (`{redis_url}`), not lab index 2.
- P2.6: `t-component-all` treats pytest exit 5 (nothing collected) as success. Services without a component suite must not fail the parallel run. `make t-component SERVICE=...` still fails on exit 5.
- P3.1: the task-service ASGI client sets `raise_app_exceptions=False`, so a failed Kafka publish is the HTTP 500 from the exception middleware.
- P3.1: the task lifecycle state machine runs Hypothesis on a worker thread and schedules each step on the session loop. `RuleBasedStateMachine` rules are synchronous, and the app clients belong to that loop.
- P3.2: the auth-service ASGI client sets `raise_app_exceptions=False`, so a failed login dependency is the HTTP 500 from the exception middleware.
- P3.2: the auth component sets `TOKEN_EXPIRE_MINUTES=45` before import. Issued-token `exp` is checked against that value.
- P3.3: the api-gateway ASGI client sets `raise_app_exceptions=False`, matching the task-service and auth-service component clients.
- P3.3: the header test pins the request respx sees. The proxy omits `host`, `sentry-trace`, `baggage`, `traceparent`, and `tracestate`. With `OTLP_ENDPOINT` empty, the httpx instrumentor puts the client's `baggage`, `traceparent`, and `tracestate` back; `sentry-trace` stays absent; `Host` is the upstream hostname.
- P3.4: the webhook-receiver ASGI client sets `raise_app_exceptions=False`, so a failed publish is the HTTP 500 from the exception middleware.
- P3.4.2: the external-service-simulator ASGI client sets `raise_app_exceptions=False`, matching the other component clients.
- P4.1: `Envelope` is `extra="forbid"`. cat-contract calls the v1 model strict. `KafkaEventReader` still builds it from the known fields, so a non-v1 message stays `event_type="unknown"`.
- P4.1: captured producer tests are collected only when `--service` is that producer. Schema and legacy tests stay in every `tests/contract` session.
