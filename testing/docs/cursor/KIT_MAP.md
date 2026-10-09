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

`TaskCreateFactory` (`ModelFactory`; `title` comes from `unique_title("task")`). `TaskRowFactory` (`SQLAlchemyFactory`, `__set_relationships__ = False`, `status` created, aware datetimes). `UserRowFactory` (one argon2 hash of `user123` in `hashed_password`; `username` fits `varchar(64)`). `.build()` does no I/O. Bind a `RunContext` before building a task factory. `seed_factories_once` calls `Factory.seed_random` once per process, from pytest-randomly. Component, contract, integration, and e2e_ui all use it.

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
- `make stack-up`, `make stack-down` (`KEEP_STACK=1` keeps the stack after a pytest run)

## P6.1 integration

`tests/integration/conftest.py`. The controller calls `stack_up` (`BASE_URL` and `NGINX_URL` when the stack is already up) and `ensure_admin_token` (FileLock, `testing/.stack/session.json`, refresh when `exp` is close). Workers read that file and do not log in. `KEEP_STACK=1` skips `down -v`.

`wait_for_stack` checks postgres, force-recreates migrations, and waits until each service kind is ready. `install_wiremock_catch_all` stubs `:8089`; `ensure_admin_token` logs in for `Stack(base_url="http://127.0.0.1:8001", nginx_url="http://127.0.0.1", owned=False)`.

`python -m saas_testkit.infra.compose wait` runs that. `--wiremock-catch-all` and `--ensure-admin-token` turn the two options on.

- `base_url`: gateway, `http://127.0.0.1:8001` unless `BASE_URL` is set.
- `nginx_url`: `NGINX_URL` or `http://127.0.0.1`.
- `admin_token`: seeded `admin` access token.
- `client`: `httpx.AsyncClient` on `base_url` with that bearer token.
- `run_context`: binds `RunContext`.
- `auth`: `AuthFlow` over `HttpAuthApi`.
- `lifecycle`: `TaskLifecycle` over `HttpTaskApi`.
- `events`: `KafkaEventReader` on `127.0.0.1:9093`, one group per worker.
- `mail`: `MailHogInbox`. `containing` returns messages whose subject or body includes the text.
- `wiremock`: `WireMockSink`. `install_catch_all` (priority 10, 200), `stub_for_payload` (JSONPath on `id`, unique scenario), `calls_for` (journal filtered by that id).

## P6.2 integration/services

`test_login_burst_without_a_bearer_is_not_limited` and `test_foreign_host_with_forwarded_headers_reaches_the_gateway` (`xdist_group("serial")`, nginx). `make t-int` uses `--dist loadgroup`.

## P6.3 integration/scenarios

`WireMockSink.stub_for_title` and `stub_sequence`. `HttpSimulatorApi.trigger` and `ExternalReceiver.trigger`. Fixtures `delivery` (`WebhookDelivery`) and `simulator` (`ExternalReceiver` on `:8000`). A session catch-all 200 is installed once. `test_created_task_reaches_kafka_mail_and_webhooks`, `test_webhook_retries_then_delivers`, `test_permanent_failure_is_replayed_without_an_idempotency_key` (`slow`), `test_triggered_event_is_published`, `test_trigger_event_is_accepted` (`xfail` BUG-8).

## P3.2 auth-service

auth-service (`tests/component/auth_service/conftest.py`): `service_app` sets `TOKEN_EXPIRE_MINUTES=45` before import and enters `lifespan_context`. `client` is `httpx.AsyncClient` on `ASGITransport` (`raise_app_exceptions=False`) with `base_url="http://test"`. `user_cache` is `UserCache`. `auth` is `AuthFlow`.

`AuthFlow.submit_login`, `me_as` (`valid`, `expired`, `tampered`, `alg_none`, `missing`, `malformed`), `ready`, `cached_user`, `replace_cached_role`. `HttpAuthApi.submit_login`, `me_header`, `ready`. `UserCache.user` and `put` (`user:{username}`, TTL 300 s). `ApiResponse.document` is the parsed JSON body. `StatusBody` is the `/ready` body.

## P3.3 api-gateway

api-gateway (`tests/component/api_gateway/conftest.py`): `service_app` enters `lifespan_context`. `client` is `httpx.AsyncClient` on `ASGITransport` (`raise_app_exceptions=False`) with `base_url="http://test"`. `gateway` is `GatewayFlow` over `HttpGatewayApi` and `GatewayUpstream` (respx).

`GatewayFlow.through`, `open`, `tasks_as` (`missing`, `expired`, `tampered`, `alg_none`), `passthrough`, `when_upstream_fails` (`timeout`, `down`), `forwarded_headers`, `allowed_origin`, and `path_for` (`auth`, `tasks`, `tasks-item`, `webhooks`). `Routed` is the response plus the upstream `service` and `path` (`None` when the gateway did not proxy). `Forwarded` is the upstream header map plus the `request_id`, `marker`, `client_host`, `upstream_host`, `baggage`, `traceparent`, and `tracestate` this call sent. `HttpGatewayApi.request` and `preflight`. `GatewayUpstream.start`, `stop`, `respond`, `fail`, `last_request`. `ProxiedBody.marker` is the JSON body the upstream double returns.

## P3.4 webhook-receiver

webhook-receiver (`tests/component/webhook_receiver/conftest.py`): `service_app` enters `lifespan_context`. `client` is `httpx.AsyncClient` on `ASGITransport` (`raise_app_exceptions=False`) with `base_url="http://test"`. `inbound` is `InboundWebhook`.

`InboundWebhook.accept`, `submit` (`missing-event`, `event-type`, `data-type`), and `published`. `Accepted` is the response plus the `event` and `data` sent. `HttpWebhookApi.receive` and `submit`. `WebhookDelivery.inbound` waits for `webhook.inbound` whose payload `event` is this call (`matches_inbound_event`). `InboundReceipt` is the 200 body (`status`, `event`).

## P3.4 external-service-simulator

external-service-simulator (`tests/component/external_service_simulator/conftest.py`): `service_app` enters `lifespan_context`. `client` is `httpx.AsyncClient` on `ASGITransport` (`raise_app_exceptions=False`) with `base_url="http://test"`. `simulator` is `ExternalReceiver`.

`ExternalReceiver.receive`, `receive_again`, and `fail` (`simulated` is `fail_rate=1`, `custom` asks for status 503). `Delivery` is the response plus the idempotency `key` and `payload` sent. `HttpSimulatorApi.receive` posts `/receive-webhook` with `Idempotency-Key`. `SimulatorReceipt` is that body (`status`, and `payload`, `idempotency_key`, `reason`, or `code`).

## P4.1 contract/events

`Envelope` is `extra="forbid"`. Snapshots: `contracts/events/task_created.schema.json`, `task_updated.schema.json`, `webhook_inbound.schema.json`, `webhook_dlq.schema.json`. `event_contract_dir` and `event_schema_errors`. `test_event_schema_matches_snapshot` and `test_legacy_message_maps_to_unknown` are service-agnostic. `test_produced_task_created_matches_snapshot` and `test_produced_task_updated_matches_snapshot` collect only for `--service task-service`. `test_produced_webhook_inbound_matches_snapshot` collects only for `--service webhook-receiver`.

## P4.2 contract/http

One session `service_app` for the selected `--service` (auth sets `TOKEN_EXPIRE_MINUTES=45` before import); event capture uses that same lifespan. `client` is the HTTP client. `fuzz_schema` is the served OpenAPI document. `check_openapi` runs Schemathesis (`not_a_server_error` and `response_schema_conformance`) on the session loop. `schema_examples` reads `SCHEMA_EXAMPLES`, default 40. Snapshots: `contracts/openapi/<service>.json` (`servers` dropped; a duplicated operationId is rewritten to `method path`). `test_openapi_document_is_valid` (api-gateway `xfail` BUG-6), `test_openapi_matches_snapshot`, `test_generated_calls_match_openapi` (task, auth, webhook-receiver; gateway and simulator skip). `test_inbound_generated_calls_are_not_server_errors` is webhook-receiver only, `xfail` BUG-5. Consumer checks: `test_created_task_matches_consumer_model`, `test_token_matches_consumer_model`, `test_me_matches_consumer_model`, `test_inbound_receipt_matches_consumer_model` (`xfail` BUG-5), `test_received_webhook_matches_consumer_model`, `test_proxied_body_matches_consumer_model`. `HttpTaskApi` sets `document` on the response.

## P7 e2e_ui

`tests/e2e_ui/conftest.py`. `base_url` and the `storage_state` origin are both `KitSettings.ui_url` (`UI_URL`, default `http://127.0.0.1:5173`). `browser_context_args` sets `service_workers=block` and `storage_state` from `session.json` (`saas_debug_token`, `frontend/src/lib/apiClient.ts`) unless the test is `@pytest.mark.anonymous`. A failure keeps a trace and a screenshot (`--tracing retain-on-failure`, `--screenshot only-on-failure`). `admin` is the seeded user. `login` is `LoginPage`. `board` is `BoardPage`. `tasks` is `UiTasks` (sync httpx on the gateway): `create` may assert, `find` returns the first title match and raises when a second exists.

`LoginPage.open`, `sign_in`, `expect_form`, `expect_login_page`, `expect_invalid_credentials`, `expect_board`. `BoardPage.open`, `reload`, `create_task`, `move_task`, `expect_open`, `expect_task`, `task_id`. `move_task` drags with `mouse.move(..., steps=40)` and waits for the move response. The context viewport is 1920×1080 so a long title does not push a column off screen. `KanbanColumn.reveal` walks the 10-card pages. `TaskCard.expect_visible` and `task_id` (the card's `title` attribute).

`test_login_with_seeded_credentials_opens_the_board` (`anonymous`, `critical`), `test_login_with_a_wrong_password_shows_an_error` (`anonymous`), `test_board_without_a_session_redirects_to_login` (`anonymous`), `test_created_task_stays_in_each_column_after_reload` (`critical`).

## P8.1 smoke

`tests/smoke/`. Reads `SMOKE_BASE_URL`. Session start exits when it is unset, unreachable, or `/health` is not 200 `{"status":"ok"}`. `ui_url` is `KitSettings.ui_url`.

`test_health_through_the_edge_is_ok` (`/health`, `/external/health`), `test_login_for_a_seeded_role_returns_a_token` (`admin`, `user`), `test_created_task_is_readable`, `test_metrics_are_reachable` (`GET /metrics`), `test_frontend_returns_ok`.

`.github/workflows/smoke.yml`: `workflow_call` and `workflow_dispatch`, inputs `smoke_base_url` and `start_stack`. `start_stack` brings the stack up on that runner; otherwise the caller has already started it.

## P8.2 synthetic

`seed_synthetic_user` inserts `SYNTHETIC_USER` with role `user` (`ON CONFLICT DO NOTHING`). `_seed` calls it when `SYNTHETIC_USER` and `SYNTHETIC_PASSWORD` are set. The published test Postgres is tried first; a refused connection inserts from the `auth-service` container. The check itself is `testing/synthetic/k6/critical_path.js` (no Python suite).

## P5 CI

`.github/workflows/ci.yml`: `lint`, `security`, `unit`, `component-contract` (matrix `task-service`, `auth-service`, `api-gateway`, `webhook-receiver`, `external-service-simulator`), `ci-gate`. `open_app_lifespan` enters a service lifespan once per process.

## P9 CI

`.github/workflows/ci.yml` also runs `integration` and `ui-e2e` (`shard: [1]`, `pytest-split --splits` / `--group`, cached `.test_durations`), `smoke` (`smoke.yml` with `start_stack`), and `coverage` (`coverage combine`). `ci-gate` needs all of them. `.github/workflows/nightly.yml`: `schemathesis` (`SCHEMA_EXAMPLES=500`), `stack` (`slow`/`chaos`, `--count 5`, `--store-durations`), `browsers` (`firefox`, `webkit`).
