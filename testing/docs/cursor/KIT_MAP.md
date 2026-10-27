# Test kit map

What `saas_testkit` offers now. Extend an entry here instead of adding a second one.

## Fixtures

In-process fixtures are `saas_testkit.plugins.in_process_service` (`src/saas_testkit/plugins/in_process_service.py`). `seed_factories` is `saas_testkit.plugins.factory_seed` (`src/saas_testkit/plugins/factory_seed.py`). Root `testing/conftest.py` registers both once with `pytest_plugins`. Neither plugin uses `autouse`.

`tests/component/conftest.py` and `tests/contract/conftest.py` turn `seed_factories` and `flush_redis` on with autouse wrappers. Component also autouses `clean_db` and `run_context`; contract autouses `run_context`. `tests/integration/conftest.py`, `tests/e2e_ui/conftest.py`, and `tests/smoke/conftest.py` depend on `seed_factories`. Unit tests do not.

The controller stores an `InfraHandle` on `config._infra`; workers load `Infra` from `workerinput["infra"]`.

- `infra`: connection URLs for this session.
- `worker_db`: `test_<service>_<layer>_<worker>` (hyphens become underscores), cloned from the migrated template and dropped at session end.
- `session_maker`, `db`: async session on that database. The app builds its own engine; do not override `get_db`.
- `service_env`: `POSTGRES_*` from `DbUrls.postgres_env()`, `REDIS_URL` for the worker index, `KAFKA_BOOTSTRAP_SERVERS`, `SERVICE_NAME`, `OTLP_ENDPOINT=""`, `SENTRY_DSN=""`. Import the app after this.
- `open_app_lifespan`: session fixture. Imports the `--service` app after `service_env` and enters its lifespan once per worker. auth-service sets `TOKEN_EXPIRE_MINUTES=45` before import. Layer `service_app` fixtures yield that app.
- `flush_redis`: `FLUSHDB` on this worker's Redis index before each test. webhook-dispatcher and notification-worker override it as a no-op (they do not use Redis; the block is shared). scheduler-worker keeps the flush.
- Worker component conftests (`webhook_dispatcher`, `notification_worker`, `scheduler_worker`) import `app.run`, `app.worker`, and `app.core.celery` after `service_env`. They do not use `open_app_lifespan`.
- `clean_db`: no-op unless the test has `@pytest.mark.clean_db`, then truncates tables listed in `_touched`.
- `run_context`: binds `RunContext` (`run_id`, `test_id`) so `unique_title` works.
- `rows`: per-test `TaskRowFactory` and `UserRowFactory` subclasses with `__async_session__` set to `db`. `create_async` commits.
- `events`: `KafkaEventReader` on `task_created`, `task_updated`, `webhook_inbound`, `webhook_dlq`, one consumer group per worker.

task-service (`tests/component/task_service/conftest.py`): `service_app` enters `lifespan_context`, `client` is `httpx.AsyncClient` on `ASGITransport` (`raise_app_exceptions=False`) with `base_url="http://test"`, `task_cache` is `TaskCache` on `app.state.redis`, `lifecycle` is `TaskLifecycle` over `HttpTaskApi`, `events`, and `task_cache`. `test_create_rejects_a_bad_title` expects 422 for an empty title, a title past 255 characters, a 10000-character title, a NUL byte, and a non-string. `test_create_accepts_a_title_at_the_length_limit` expects 201 at 255 characters. The `tasks.title` column stays unbounded.

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

`tests/integration/conftest.py`. The test stack project is `saas-test`. Compose must be at least 2.24, and `compose.py` refuses to start when `COMPOSE_PROJECT_NAME` is set to anything else. Published host ports: gateway `8010`, nginx `9080`, frontend `5174`, simulator `8002`, mailhog `8026`, Kafka `9095`, Postgres `5434`, Redis `6381`, toxiproxy `8475`. Worker metrics are `9111`–`9113`. WireMock stays on `8089`. The synthetic probe still targets the dev lab.

The controller calls `stack_up` (`BASE_URL` and `NGINX_URL` when the stack is already up) and `ensure_admin_token` (FileLock, `testing/.stack/session.json`). Reuse requires the compose project, the postgres container id, a stored token that is not near `exp`, and a live admin login. Otherwise it seeds and logs in. Workers read that file and do not log in. `KEEP_STACK=1` skips `down -v`.

`wait_for_stack` checks postgres, force-recreates migrations, and waits until each service kind is ready. `install_wiremock_catch_all` stubs `:8089`; `ensure_admin_token` logs in for `Stack(base_url="http://127.0.0.1:8010", nginx_url="http://127.0.0.1:9080", owned=False)`.

`python -m saas_testkit.infra.compose wait` runs that. `--wiremock-catch-all` and `--ensure-admin-token` turn the two options on.

- `base_url`: gateway, `http://127.0.0.1:8010` unless `BASE_URL` is set.
- `nginx_url`: `NGINX_URL` or `http://127.0.0.1:9080`.
- `admin_token`: seeded `admin` access token.
- `client`: `httpx.AsyncClient` on `base_url` with that bearer token.
- `run_context`: binds `RunContext`.
- `auth`: `AuthFlow` over `HttpAuthApi`.
- `lifecycle`: `TaskLifecycle` over `HttpTaskApi`.
- `events`: `KafkaEventReader` on `127.0.0.1:9095`, one group per worker.
- `mail`: `MailHogInbox` at `http://127.0.0.1:8026`. `containing` returns messages whose subject or body includes the text.
- `wiremock`: `WireMockSink`. `install_catch_all` (priority 10, 200), `stub_for_payload` (JSONPath on `id`, unique scenario), `calls_for` (journal filtered by that id).

## P6.2 integration/services

`test_login_burst_without_a_bearer_is_not_limited` and `test_foreign_host_with_forwarded_headers_reaches_the_gateway` (`xdist_group("serial")`, nginx). `make t-int` uses `--dist loadgroup`.

## P6.3 integration/scenarios

`WireMockSink.stub_for_title` and `stub_sequence`. `HttpSimulatorApi.trigger` and `ExternalReceiver.trigger`. Fixtures `delivery` (`WebhookDelivery`) and `simulator` (`ExternalReceiver` on `:8002`). A session catch-all 200 is installed once. `test_created_task_reaches_kafka_mail_and_webhooks`, `test_webhook_retries_then_delivers`, `test_permanent_failure_is_replayed_without_an_idempotency_key` (`slow`), `test_triggered_event_is_published`, `test_trigger_event_is_accepted` (202, `status` `triggered`).

## P3.2 auth-service

auth-service (`tests/component/auth_service/conftest.py`): `service_app` sets `TOKEN_EXPIRE_MINUTES=45` before import and enters `lifespan_context`. `client` is `httpx.AsyncClient` on `ASGITransport` (`raise_app_exceptions=False`) with `base_url="http://test"`. `user_cache` is `UserCache`. `auth` is `AuthFlow`.

`AuthFlow.submit_login`, `me_as` (`valid`, `expired`, `tampered`, `alg_none`, `missing`, `malformed`), `ready`, `cached_user`, `replace_cached_role`. `HttpAuthApi.submit_login`, `me_header`, `ready`. `UserCache.user` and `put` (`user:{username}`, TTL 300 s). The cache write runs only after the password check succeeds. `test_wrong_password_leaves_no_user_cache`: a wrong password is 401 and leaves no `user:{username}`. `test_user_cache_omits_the_password_hash` is `xfail(strict=True)` (BUG-4b): a successful login still stores `hashed_password`. `ApiResponse.document` is the parsed JSON body. `StatusBody` is the `/ready` body.

## P3.3 api-gateway

api-gateway (`tests/component/api_gateway/conftest.py`): `service_app` enters `lifespan_context`. `client` is `httpx.AsyncClient` on `ASGITransport` (`raise_app_exceptions=False`) with `base_url="http://test"`. `gateway` is `GatewayFlow` over `HttpGatewayApi` and `GatewayUpstream` (respx).

`GatewayFlow.through`, `open`, `tasks_as` (`missing`, `expired`, `tampered`, `alg_none`), `passthrough`, `when_upstream_fails` (`timeout`, `down`), `forwarded_headers`, `allowed_origin`, and `path_for` (`auth`, `tasks`, `tasks-item`, `webhooks`). `Routed` is the response plus the upstream `service` and `path` (`None` when the gateway did not proxy). `Forwarded` is the upstream header map plus the `request_id`, `marker`, `client_host`, `upstream_host`, `baggage`, `traceparent`, and `tracestate` this call sent. `HttpGatewayApi.request` and `preflight`. `GatewayUpstream.start`, `stop`, `respond`, `fail`, `last_request`. `ProxiedBody.marker` is the JSON body the upstream double returns.

## P3.4 webhook-receiver

webhook-receiver (`tests/component/webhook_receiver/conftest.py`): `service_app` enters `lifespan_context`. `client` is `httpx.AsyncClient` on `ASGITransport` (`raise_app_exceptions=False`) with `base_url="http://test"`. `inbound` is `InboundWebhook`.

`InboundWebhook.accept`, `submit` (`missing-event`, `event-type`, `data-type`), and `published`. `Accepted` is the response plus the `event` and `data` sent. `HttpWebhookApi.receive` and `submit`. `WebhookDelivery.inbound` waits for `webhook.inbound` whose payload `event` is this call (`matches_inbound_event`). `InboundReceipt` is the 200 body (`status`, `event`).

## P3.4 external-service-simulator

external-service-simulator (`tests/component/external_service_simulator/conftest.py`): `service_app` enters `lifespan_context`. `client` is `httpx.AsyncClient` on `ASGITransport` (`raise_app_exceptions=False`) with `base_url="http://test"`. `simulator` is `ExternalReceiver`.

`ExternalReceiver.receive`, `receive_again`, and `fail` (`simulated` is `fail_rate=1`, `custom` asks for status 503). `Delivery` is the response plus the idempotency `key` and `payload` sent. `HttpSimulatorApi.receive` posts `/receive-webhook` with `Idempotency-Key`. `SimulatorReceipt` is that body (`status`, and `payload`, `idempotency_key`, `reason`, or `code`).

## R-3.1 webhook-dispatcher

`tests/component/webhook_dispatcher/`. Tests call `process_consumed_message` (the consume loop stays down). respx answers `WEBHOOK_URL`. `asyncio.sleep` and `random.uniform` are patched (`autospec`); jitter is pinned so the default waits are `1.05` then `2.15`, and nothing is slept after the last attempt. `kafka_producer` is a real `AIOKafkaProducer`; `WebhookDelivery.dead_letter` reads `webhook_dlq`. A produce failure is an autospec `AIOKafkaProducer` whose `send_and_wait` raises; `kafka_produce_failed` is logged and the call returns.

`deliver` posts one record. `test_webhook_posts_once_when_receiver_returns_2xx` (`Idempotency-Key` is `str(payload.id)`), `test_webhook_retries_with_backoff_when_delivery_fails` and `test_webhook_dead_letters_when_retries_are_exhausted` (`5xx`, `httpx.RequestError`), `test_webhook_dead_letters_without_retry_when_receiver_returns_4xx`, `test_webhook_posts_raw_json_when_message_is_legacy`, `test_consumer_returns_when_message_is_poison` (no `webhook_dlq`), `test_consumer_logs_and_returns_when_dlq_produce_fails`.

## R-3.2 notification-worker

`tests/component/notification_worker/`. Tests call `consume` with a stand-in consumer (the real consumer stays down). `aiosmtplib.send` is patched (`autospec`) and the `MIMEMultipart` is captured. No SMTP.

`mail_settings` is `email_from`, `email_to`, `smtp_host`. `test_notification_sends_multipart_mail_when_a_task_is_created` (`multipart/alternative`; text and html both contain the title; subject, from, and to come from settings; `emails_total` `success`), `test_notification_sends_the_next_message_when_smtp_fails` (`SMTPException` → `smtp_error`, `OSError` → `connection_error`; the next message is still sent), `test_notification_sends_only_the_valid_mail_when_the_previous_message_is_poison` (`b"{"` then a valid task; one mail), `test_notification_sends_mail_when_message_is_legacy`.

## R-3.3 scheduler-worker

`tests/component/scheduler_worker/`. Cleanup calls `cleanup_old_tasks.apply` against the worker database (sync psycopg2 engine from `POSTGRES_*`). Those tests are `@pytest.mark.clean_db` and insert with `rows.task.create_async` and an explicit `updated_at`. `cleanup_completed_tasks_minutes` is monkeypatched. Replay calls `retry_single_webhook.apply` (eager). respx answers `WEBHOOK_URL`. The DLQ drain stays down.

`test_cleanup_deletes_only_completed_tasks_older_than_the_threshold` (completed just inside the cutoff is deleted; just outside, `in_progress`, and `created` stay), `test_cleanup_deletes_nothing_when_the_threshold_is_zero`, `test_replay_is_final_when_the_receiver_returns_an_http_error` (4xx and 5xx, one POST, no `Idempotency-Key`), `test_replay_retries_when_the_request_fails` (`httpx.RequestError`, `max_retries` 5), `test_replay_retries_when_the_receiver_returns_5xx` (`xfail` BUG-12).

## P4.1 contract/events

`Envelope` is `extra="forbid"`. Snapshots: `contracts/events/task_created.schema.json`, `task_updated.schema.json`, `webhook_inbound.schema.json`, `webhook_dlq.schema.json`. `event_contract_dir` and `event_schema_errors`. `test_event_schema_matches_snapshot` and `test_legacy_message_maps_to_unknown` are service-agnostic. `test_produced_task_created_matches_snapshot` and `test_produced_task_updated_matches_snapshot` collect only for `--service task-service`. `test_produced_webhook_inbound_matches_snapshot` collects only for `--service webhook-receiver`.

## P4.2 contract/http

One session `service_app` for the selected `--service` (auth sets `TOKEN_EXPIRE_MINUTES=45` before import); event capture uses that same lifespan. `client` is the HTTP client. `fuzz_schema` is the served OpenAPI document. `check_openapi` runs Schemathesis (`not_a_server_error` and `response_schema_conformance`) on the session loop. `schema_examples` reads `SCHEMA_EXAMPLES`, default 40. Snapshots: `contracts/openapi/<service>.json` (`servers` dropped). `test_openapi_document_is_valid` and `test_openapi_matches_snapshot` run for every `--service`. The gateway document validates: each proxy method has its own operationId, and `contracts/openapi/api-gateway.json` keeps those ids. `test_generated_calls_match_openapi` covers task-service, auth-service, and webhook-receiver; the gateway and the simulator skip it. `test_login_with_a_nul_username_is_not_a_server_error` is auth-service only: a NUL byte in the username is 422, and the check asserts the status is under 500. Consumer checks: `test_created_task_matches_consumer_model`, `test_token_matches_consumer_model`, `test_me_matches_consumer_model`, `test_inbound_receipt_matches_consumer_model`, `test_received_webhook_matches_consumer_model`, `test_proxied_body_matches_consumer_model`. `HttpTaskApi` sets `document` on the response.

## P7 e2e_ui

`tests/e2e_ui/conftest.py`. `base_url` and the `storage_state` origin are both `KitSettings.ui_url` (`UI_URL`, default `http://127.0.0.1:5174`). `browser_context_args` sets `service_workers=block` and `storage_state` from `session.json` (`saas_debug_token`, `frontend/src/lib/apiClient.ts`) unless the test is `@pytest.mark.anonymous`. A failure keeps a trace and a screenshot (`--tracing retain-on-failure`, `--screenshot only-on-failure`). `admin` is the seeded user. `login` is `LoginPage`. `board` is `BoardPage`. `tasks` is `UiTasks` (sync httpx on the gateway): `create` may assert, `find` returns the first title match and raises when a second exists.

`LoginPage.open`, `sign_in`, `expect_form`, `expect_login_page`, `expect_invalid_credentials`, `expect_board`. `BoardPage.open`, `reload`, `create_task`, `move_task`, `expect_open`, `expect_task`, `task_id`. `move_task` drags with `mouse.move(..., steps=40)` and waits for the move response. The context viewport is 1920×1080. A title with no spaces wraps inside the column. `KanbanColumn.reveal` walks the 10-card pages. `TaskCard.expect_visible` and `task_id` (the card's `title` attribute).

`test_login_with_seeded_credentials_opens_the_board` (`anonymous`, `critical`), `test_login_with_a_wrong_password_shows_an_error` (`anonymous`), `test_board_without_a_session_redirects_to_login` (`anonymous`), `test_created_task_stays_in_each_column_after_reload` (`critical`).

## P8.1 smoke

`tests/smoke/`. Reads `SMOKE_BASE_URL`. Session start exits when it is unset, unreachable, or `/health` is not 200 `{"status":"ok"}`. `ui_url` is `KitSettings.ui_url`.

`test_health_through_the_edge_is_ok` (`/health`, `/external/health`), `test_login_for_a_seeded_role_returns_a_token` (`admin`, `user`), `test_created_task_is_readable`, `test_metrics_are_reachable` (`GET /metrics`), `test_frontend_returns_ok`.

`.github/workflows/smoke.yml`: `workflow_call` and `workflow_dispatch`, inputs `smoke_base_url` and `start_stack`. `start_stack` brings the stack up on that runner; otherwise the caller has already started it. `ci.yml` runs this suite as a step inside `integration` (`SMOKE_BASE_URL=http://127.0.0.1:9080`, `UI_URL=http://127.0.0.1:5174`). `smoke.yml` stays the post-deploy workflow.

## P8.2 synthetic

`seed_synthetic_user` inserts `SYNTHETIC_USER` with role `user` (`ON CONFLICT DO NOTHING`). `_seed` calls it when `SYNTHETIC_USER` and `SYNTHETIC_PASSWORD` are set. The published test Postgres is tried first; a refused connection inserts from the `auth-service` container. The check itself is `testing/synthetic/k6/critical_path.js` (no Python suite).

## P5 CI

`.github/workflows/ci.yml`: `lint`, `security`, `unit`, `component-contract` (needs `security`; matrix `task-service`, `auth-service`, `api-gateway`, `webhook-receiver`, `external-service-simulator`, `webhook-dispatcher`, `notification-worker`, `scheduler-worker`), `ci-gate`. `changes` sets `services` to the touched names in that matrix (all eight on main). `stack` is true on main, or on a pull request when any of those services, `frontend/**`, `testing/**`, `shared/**`, `infra/**`, `migrations/**`, `.github/**`, or a `uv.lock` changed. `docs/**` alone leaves `services` empty and `stack` false, so `component-contract`, `build`, `integration`, `ui-e2e`, and `coverage` stay skipped. `ci-gate` still treats `skipped` as success. `coverage` measures component and contract for each service plus `shared/saas_shared` (branch coverage, combined total 81%). A push to `main` fails under 80% (drift guard; ratchet to 85 as shared gets covered). A pull request runs diff-cover at 85% on changed lines; a diff with no Python lines passes. Unit self-tests, integration, e2e, smoke, and synthetic stay out of that total: those services run in containers, so `--cov` cannot see them. `open_app_lifespan` enters a service lifespan once per worker. Nightly Schemathesis stays the five HTTP services.

## P9 CI

`.github/workflows/ci.yml` also runs `build` (the only cache writer; integration and ui-e2e bake with `cache-from: type=gha`), `integration`, `ui-e2e` (`shard: [1]`, `--randomly-seed` from `github.run_id`, `pytest-split --splits` / `--group`, cached `.test_durations`), and `coverage` (combine of component and contract, per service, plus `shared/saas_shared`, with branch coverage; measured total 81%; HTML artifact `coverage-html`; XML artifact `coverage-xml`; markdown summary). Unit self-tests, integration, e2e, smoke, and synthetic are not in that total: those services run in containers, so `--cov` cannot see them, and scenario and edge coverage is the measure for those layers. A push to `main` runs `coverage report --fail-under=80` (drift guard; ratchet to 85 as shared gets covered). A pull request runs `diff-cover coverage.xml --compare-branch=origin/<base> --fail-under=85`. The combined pull request report is partial because of the path filter; diff-cover only looks at changed lines, and a diff with no Python lines passes. Smoke is a step inside `integration`. A pull request runs `build`, `integration`, and `ui-e2e` when `stack` is true, including a change to only one service. Integration uses `-m "not slow and not chaos"` and ui-e2e uses `-m critical`. A `docs/**`-only pull request skips those jobs. A main push runs integration with `-m "not chaos"` (`slow` included) and the full UI suite. `chaos` stays on nightly. `ci-gate` (`if: always()`) needs `changes`, `lint`, `security`, `unit`, `component-contract`, `build`, `integration`, `ui-e2e`, and `coverage`. `success` or `skipped` pass; `failure` and `cancelled` fail. `.github/workflows/nightly.yml`: `schemathesis` (`SCHEMA_EXAMPLES=500`; Schemathesis sends NUL bytes, and a NUL username is 422; Postgres rejects `0x00` in other text columns), `stack` (`slow`/`chaos`, `--count 5`, `--store-durations`), `browsers` (`firefox`, `webkit`). The flaky pass and the duration refresh run `tests/integration` and `tests/e2e_ui` in separate pytest processes. The UI flaky pass uses `--reruns 1`. The report job sets `GH_REPO` and does not checkout.
