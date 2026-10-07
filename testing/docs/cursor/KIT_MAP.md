# Test kit map

What `saas_testkit` offers now. Extend an entry here instead of adding a second one.

## Fixtures

Component session (`tests/component/conftest.py`). The controller stores an `InfraHandle` on `config._infra`; workers load `Infra` from `workerinput["infra"]`.

- `infra`: connection URLs for this session.
- `worker_db`: `test_<service>_<layer>_<worker>` (hyphens become underscores), cloned from the migrated template and dropped at session end.
- `session_maker`, `db`: async session on that database. The app builds its own engine; do not override `get_db`.
- `service_env`: `POSTGRES_*` from `DbUrls.postgres_env()`, `REDIS_URL` for the worker index, `KAFKA_BOOTSTRAP_SERVERS`, `SERVICE_NAME`, `OTLP_ENDPOINT=""`, `SENTRY_DSN=""`. Import the app after this.
- `flush_redis`: `FLUSHDB` on this worker's Redis index before each test.
- `clean_db`: no-op unless the test has `@pytest.mark.clean_db`, then truncates tables listed in `_touched`.
- `run_context`: binds `RunContext` (`run_id`, `test_id`) so `unique_title` works.
- `rows`: per-test `TaskRowFactory` and `UserRowFactory` subclasses with `__async_session__` set to `db`. `create_async` commits.
- `events`: `KafkaEventReader` on `task_created`, `task_updated`, `webhook_inbound`, `webhook_dlq`, one consumer group per worker.

task-service (`tests/component/task_service/conftest.py`): `service_app` enters `lifespan_context`, `client` is `httpx.AsyncClient` on `ASGITransport` (`raise_app_exceptions=False`) with `base_url="http://test"`, `task_cache` is `TaskCache` on `app.state.redis`, `lifecycle` is `TaskLifecycle` over `HttpTaskApi`, `events`, and `task_cache`.

## Flows and adapters

`TaskLifecycle.create`, `submit_title`, `list_tasks`, `get`, `start`, `complete`, `move`, and `move_missing` return `ApiResponse` and do not assert. `new_task`, `move_to_completed`, and `at_status` are preconditions and may assert. `task_created_event` delegates to `WebhookDelivery.task_created`; `task_updated_event` delegates to `WebhookDelivery.task_updated` (same id compare, `str(task_id)`). `replace_cached_title`, `replace_cached_list`, `drop_cached_task`, and `drop_cached_list` read or write the task Redis keys.

`AuthFlow.login` and `me` return `ApiResponse` and do not assert. `logged_in` is a precondition and may assert.

`WebhookDelivery.task_created`, `task_updated`, and `dead_letter` wait with `eventually` and do not assert. No WireMock journal and no retry timing.

`HttpTaskApi`: `create`, `submit` (JSON object for a bad title), `list_tasks`, `get` (UUID or string id), `start`, `complete`. `HttpAuthApi`: `login` (`POST /auth/token` form), `me` (`GET /auth/me` bearer). `KafkaEventReader`: `start`, `stop`, `wait_for`. `TaskCache`: `item`, `put_item`, `drop_item` (`tasks:{id}`), `put_list`, `drop_list` (`tasks:list`).

## Factories

`TaskCreateFactory` (`ModelFactory`; `title` comes from `unique_title("task")`). `TaskRowFactory` (`SQLAlchemyFactory`, `__set_relationships__ = False`, `status` created, aware datetimes). `UserRowFactory` (one argon2 hash of `user123` in `hashed_password`; `username` fits `varchar(64)`). `.build()` does no I/O. Bind a `RunContext` before building a task factory. One `Factory.seed_random` per run, from pytest-randomly.

Envelope factories (`TaskCreated`, `TaskUpdated`, `WebhookInbound`, `WebhookDlq`) build a v1 `Envelope`. Payload models are `TaskCreatedPayload`, `TaskUpdatedPayload` (`id`, `title`, `status`), `WebhookInboundPayload` (`event`, `data`), and `WebhookDlqPayload` (task fields plus `error`, `attempts`, `timestamp`). `JwtFactory` mints `sub` / `role` / `exp` tokens: `valid`, `expired`, `tampered` (payload changed, signature kept), `alg_none`. Default secret is the lab `dev-secret-change-in-production`.

## Markers

Root `conftest.py` marks a test from its directory: `unit`, `contract`, `component`, `integration`, `e2e_ui`, `smoke`, `synthetic`. Opt-in: `slow`, `chaos`, `critical`, `clean_db`. `--service <name>` is one service per component or contract session and ignores the other component directories. Infra starts only when `--service` is set or `INFRA=on`, and never for `integration`, `e2e_ui`, `smoke`, or `synthetic`.

## Make targets

Repo root, via `testing/testing.mk`. `TEST_PG_URL`, `TEST_REDIS_URL`, and `TEST_KAFKA_BOOTSTRAP` are exported, so these runs use `compose.deps.yml` unless the variables are unset. Component and contract need `uv sync --group <service>` first; a plain `uv sync` does not install that group.

- `make deps-up`, `deps-down`, `deps-clean`
- `make t-unit`
- `make t-component SERVICE=task-service`, `make t-component-all`
- `make t-contract` (`SERVICE` for `tests/contract/http`), `make contracts-update`
- `make t-int`, `t-ui`, `t-smoke`, `t-synthetic`
- `make t-lint`, `t-check`, `t-gate` (`LAYER=`; `SERVICE=` for component and contract)
