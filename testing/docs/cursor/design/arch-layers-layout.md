# Testing architecture: pyramid, layer matrix, repo layout, SUT cheat sheet

## Pyramid (top = few, bottom = most)
smoke (post-deploy gate) / synthetic (continuous, prod)
e2e_ui (Playwright)
integration (compose, network)
component (service + real PG/Redis/Redpanda)
contract (OpenAPI / events / snapshots / Schemathesis)
unit (pure code, mocker)

## Layer matrix
- unit: no infra; isolation = process; -n auto; every PR.
- contract: in-proc; worker DB; worker Redis DB index; Redpanda; respx; worker DB + unique data; -n auto; PR 25-50 examples, nightly 500+ stateful.
- component: in-proc; worker DB with real commits; worker Redis DB index + FLUSHDB per test; Redpanda; respx; unique data, clean_db on demand; -n auto; every PR.
- integration: containers; shared stack PG/Redis; real Kafka; WireMock / simulator; unique data; -n 3; PR fast subset, push to main full.
- e2e_ui: containers; shared stack; real Kafka; context per test, unique data; -n 2; PR -m critical, push to main full chromium, nightly cross-browser.
- smoke: target URL (fresh stack/staging/prod); smoke user, unique data; one process; PR (against built stack) + after every deploy; blocks.
- synthetic: target URL (prod/staging); dedicated synthetic user, synthetic- data; one process; cron every 5 min (API), 30 min (browser); alerts, never blocks.

## Repository layout
testing/
  pyproject.toml   # ONE toml: package (hatchling, src/saas_testkit), deps, pytest, ruff (src=["src","tests"]), pyright, coverage
  uv.lock  .python-version  testing.mk  README.md  KNOWN_ISSUES.md
  conftest.py      # markers by path, --service, sys.path, controller infra, xdist hooks, failure links
  compose.deps.yml # optional pg+redis(+redpanda) for local runs (TEST_PG_URL / TEST_REDIS_URL / TEST_KAFKA_BOOTSTRAP)
  contracts/       # committed snapshots: openapi/<svc>.json, events/*.schema.json
  docs/            # human docs, SUT_MAP.md, cursor/ (agent-facing pack: design/, plan/, INDEX.md, KIT_MAP.md)
  src/saas_testkit/   # installable package (src-layout, hatchling, py.typed): from saas_testkit.flows import ...
    config/      # settings.py (pydantic-settings), services.py (name -> path, module, port, DI seams; real paths are services/core/*, services/external/*, workers/*)
    domain/      # Pydantic v2 boundary models: tasks, users, webhooks, events (Envelope v1, payloads), enums
    ports/       # Protocols only if >= 2 implementations appear (none at start)
    adapters/
      http/      # HttpTaskApi, HttpAuthApi (one client, injectable transport), retry/backoff policy
      kafka/     # KafkaEventReader (aiokafka, unique consumer group; real Redpanda/Kafka)
      redis/     # DB index per worker, flush
      postgres/  # session helpers (sync + async)
      mail/      # MailHogInbox
      wiremock/  # WireMockSink (stubs + request journal)
      toxiproxy/ # ToxiproxyControl (latency/timeout/reset toxics)
      playwright/# pages/, components/
    factories/   # Polyfactory: payloads.py (ModelFactory), rows.py (SQLAlchemyFactory), events.py, builders.py, providers.py
    flows/       # task_lifecycle.py, auth.py, webhook_delivery.py, inbound_webhook.py (business language)
    infra/       # containers.py (env-or-container), template_db.py, app_loader.py, compose.py (up/wait/down/KEEP_STACK), xdist.py
    context.py   # RunContext(run_id, test_id), unique_title(), correlation / W3C traceparent
    polling.py   # eventually()
    reporting.py # on failure: correlation id + Jaeger/Kibana search links
  tests/
    unit/        # saas_testkit self-tests (factories, polling, envelope models, backoff helper)
    contract/{http,events}/
    component/{task_service,auth_service,api_gateway,webhook_receiver,external_service_simulator,webhook_dispatcher,notification_worker,scheduler_worker}/
    integration/{services,scenarios}/
    e2e_ui/task_lifecycle/
    smoke/       # post-deploy gate
    synthetic/   # continuous critical-path checks (api/, browser/)
Plus testing/synthetic/k6/critical_path.js (non-Python asset for Grafana Synthetic Monitoring, stretch).
Every tests/<layer>/ has its own conftest.py (fixtures for that layer only); root conftest = cross-layer infra only.
Service unit tests (later) live next to each service (services/core/<svc>/tests/unit, services/external/<svc>/tests/unit, workers/<svc>/tests/unit) and reuse saas_testkit.factories. Add the kit as a path dependency: `uv add --dev ../../../testing` from services/core/<svc> and services/external/<svc>, `uv add --dev ../../testing` from workers/<svc>. Fixtures stay in conftest.py; if services' unit tests need them, extract saas_testkit.pytest_plugin (entry point) then, not before.

## SUT cheat sheet (from ARCHITECTURE.md; provisional until SUT_MAP.md is built in P0, which wins on any conflict)
- nginx :80 -> api-gateway. Rate-limit zones are keyed by the Authorization header, not by IP: API 20 r/s burst 100 (delayed) on /, burst 20 nodelay on /webhooks/; /auth/token 5 r/min burst 3. A login request has no Authorization header, so it is probably not limited at all (BUG candidate for KNOWN_ISSUES.md). The API limit is per bearer token, so one shared token file means one shared bucket.
- api-gateway :8000 (FastAPI) -> auth, task, webhook-receiver. JWT HS256 required only for /tasks/*; strips Host/sentry-trace/baggage; CORS for :5173.
- auth-service (FastAPI + PG + Redis db1): POST /auth/token (form), GET /auth/me; users admin/admin123, user/user123 (seed script, not automatic); user cache TTL 300.
- task-service (FastAPI + PG + Redis db0 + Kafka producer): /tasks CRUD, PATCH /tasks/{id}/start (other transition routes: SUT_MAP); list/item cache in Redis; emits task_created / task_updated.
- webhook-receiver (FastAPI + Kafka producer): POST /webhooks/inbound -> topic webhook_inbound.
- webhook-dispatcher (Kafka consumer, no HTTP, metrics :9100) -> WEBHOOK_URL: consumes task_created/updated; POST with Idempotency-Key; backoff 1/2/4 s +-10 %; 4xx no retry; permanent failure -> webhook_dlq.
- external-service-simulator (FastAPI): /receive-webhook (fail_rate, delay, status, idempotency dedupe), /trigger-event -> gateway /webhooks/inbound.
- notification-worker (Kafka consumer) -> Toxiproxy -> MailHog: task_created -> email (MIME text+html); MailHog API :8025.
- scheduler-worker (Celery + Beat; Redis db2, Kafka, PG): retry_failed_webhooks every 60 s (drain DLQ), cleanup_old_tasks every 5 min.
- Kafka envelope v1: event_type, version, trace_id, timestamp, payload; legacy raw JSON -> event_type="unknown".
- frontend :5173 (React Kanban) -> gateway: drag-and-drop between columns, login page.
