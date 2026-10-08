# Known issues

## Defects

### Confirmed

- BUG-1: nginx `location /auth/token` is `limit_req zone=auth` at `5r/m` burst 3, keyed by `$http_authorization`. Ten logins within a few seconds, with no `Authorization` header, all return 200. An empty zone key is not accounted, so the documented limit does not apply.
- BUG-2: task-service `TaskCreate.title` is an unconstrained string. `POST /tasks` stores an empty title and a 10000-character title and returns 201. Expected 422. `xfail(strict=True)` on those two cases. A non-string title does return 422.
- BUG-3: task-service commits in the repository, then calls `publish_event`. A Kafka failure returns 500, the task row remains (a create stays stored, a start stays `in_progress`), the event is not published, and `cache_delete` does not run. `xfail(strict=True)` on create and start.
- BUG-4: auth-service login writes `hashed_password` to Redis (`user:{username}`, TTL 300 s) before it checks the password. `xfail(strict=True)` expects that cache entry to omit the hash. A second login reads the cached row.
- BUG-5: webhook-receiver `receive_inbound` logs `event=<payload event>` after a successful publish, and the failure log does the same. structlog already takes that name as the message, so the call raises `TypeError` and the route returns 500 instead of 200. The Kafka message is published before the success log. `xfail(strict=True)` on the 200 response, on the consumer-model check, and on Schemathesis for `POST /webhooks/inbound`.
- BUG-6: api-gateway OpenAPI reuses operationIds across methods (`proxy_auth_auth__path__post`, and the same pattern on `/tasks`, `/tasks/{path}`, and `/webhooks/{path}`). Which method name wins changes between processes. `openapi-spec-validator` rejects the document. `GET /openapi.json` is still 200. `xfail(strict=True)` on document validity. The snapshot rewrites a duplicated operationId to `method path` and pins the rest.
- BUG-7: webhook-dispatcher sets `Idempotency-Key` to `str(payload.id)`. `task_created` and both `task_updated` deliveries for one task share that key.
- BUG-8: external-service-simulator `trigger_event` logs `event=body.event`. structlog already uses that name, so the call raises `TypeError` and `POST /trigger-event` returns 500 instead of 202. The background POST is scheduled before the log. `xfail(strict=True)` on the 202 response.

### Candidates to confirm

Confirm in the layer that can observe the behaviour, then assign a BUG-n and `xfail(strict=True)`.

- Scheduler DLQ replay is final on any `httpx.HTTPStatusError` (`autoretry_for` is only `httpx.RequestError`). The DLQ consumer sets `enable_auto_commit=True` and `process_dlq` commits by consuming and closing before the Celery task performs the HTTP call, so a rejected replay is not returned to `webhook_dlq`.
- Dispatcher `_produce` logs `kafka_produce_failed` and does not re-raise. Notification-worker catches `aiosmtplib.SMTPException` and `OSError`, counts them, and does not re-raise.
- The `role` claim is written at login and copied by gateway `verify_token` and `/auth/me`. No route checks it. There is no authZ.
- `GET /tasks` returns every row (`list_all`; no limit or offset).

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
- P4.2: `HttpTaskApi` sets `ApiResponse.document`, matching the other HTTP adapters, so a contract test can `model_validate` the raw body.
- P4.2: Schemathesis sends on the pytest session loop via `httpx`. `from_asgi` drives a second lifespan and another loop, which breaks the async engine. `SCHEMA_EXAMPLES` defaults to 40. `POST /webhooks/inbound` is omitted from the shared fuzz test and run on its own under `xfail` BUG-5.
- P5: `ci-gate` sets `working-directory` to the workspace. The workflow default is `testing/`, and that job does not checkout, so the directory would be missing.
- P5: `setup-uv` sets `python-version` 3.14. The kit requires it, and setup-uv looks for `pyproject.toml` in the repo root, which has none.
- P5: `open_app_lifespan` enters the service lifespan once. Component and contract each have a session fixture, and one pytest process runs both; a second startup replaces the Kafka producer.
- P5: `worker_db` clones once per process, and `_seed_factories` seeds once. The contract conftest imports the component fixtures, so pytest registers them again. A second clone runs `pg_terminate_backend` (`connection is closed`). A second `seed_random` rewinds ids already inserted in that database.
- P6.1: host Postgres is `5433` and Redis is `6380`, because `compose.deps.yml` already binds `5432` and `6379`. `DATABASE_URL` overrides the seed URL. `WEBHOOK_BACKOFF_BASE=0.2`, `DLQ_REPLAY_INTERVAL_SECONDS=5`, `CLEANUP_INTERVAL_SECONDS=10`. `CLEANUP_COMPLETED_TASKS_MINUTES` stays at the default 5.
- P6.1: Postgres keeps `shared_preload_libraries=pg_stat_statements` so `infra/postgres/init.sql` still runs, and adds the ADR-18 flags. The data directory is `PGDATA=/tmp/pgdata` on tmpfs. Compose 2.19 appends volumes, so the base `postgres_data` mount cannot be removed. `test-stack.services` drops ZooKeeper and adds WireMock.
- P6.2: `make t-int` passes `--dist loadgroup` so the nginx `serial` group stays on one worker.
- P6.2: health through the gateway and the `/metrics` series stay in smoke. `arch-integration.md` lists them as T2.
- P6.2: `X-Forwarded-For`, `X-Forwarded-Proto`, and `Host` are not on the HTTP response, and Jaeger is not in the test stack. The edge test sends a foreign Host plus those headers and asserts `/health` is 200 and `X-Request-ID` is echoed.
- P6.3: S4 stays inside S1 (the shared `Idempotency-Key`). S5 is not in the integration catalogue, so there is no chaos scenario. S2a is not `slow`; only the DLQ replay (S2b) is.
- P6.3: webhook stubs match the task title. The title is known before create; `payload.id` is assigned on insert, and the dispatcher can POST before a stub on that id exists.
- P6.3: the test stack sets the simulator `INTEGRATION_SERVICE_WEBHOOK_URL` to `http://api-gateway:8000/webhooks/inbound`. The lab value `http://localhost/webhooks/inbound` is the simulator itself inside its container.
