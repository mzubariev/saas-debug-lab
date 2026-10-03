# Testing Architecture — saas-debug-lab

Source of truth: `test-infra-architecture.md` (isolation, sharing, CI DAG) + author notes. This file adapts them to **this** monorepo. Rules for Cursor: `.cursor/rules/` (`python-style`, `testing-core`, `playwright`, `testing-modify-prod`). Task order: `IMPLEMENTATION_PLAN.md`.

## 1. Goals and non-goals

**Goal:** a framework that shows Senior SDET skills: layered pyramid, typed Python 3.14, ports/adapters, parallel-safe isolation, cheap shared infra, distributed-system testing (Kafka, retries, DLQ, idempotency, eventual consistency), Playwright done right, a fast gated CI.
**Non-goals now:** fixing/refactoring the lab, unit tests for services (the kit supports them; written after refactor), real deploy.

## 1.1 Terms (use consistently)


| Term                        | Meaning                                                                                 |
| --------------------------- | --------------------------------------------------------------------------------------- |
| CI run → job                | one pipeline run → one matrix entry (service, shard, browser)                           |
| runner / node / VM          | machine executing a job                                                                 |
| pytest session (controller) | OS process (python/pytest) that starts infra, builds the template DB and spawns workers |
| xdist worker                | child OS process (`gw0`, `gw1`) that runs tests; own DB, own Redis prefix               |
| scale-up                    | more workers (`-n N`) on one stack; scale-out                                           |




## 2. Key decisions (ADRs)


| #   | Decision                                                                                                                                                                                                                                                                                                                                                                                    | Why / trade-off                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **One service per pytest session (controller + its workers)** for component + contract (`--service task-service`)                                                                                                                                                                                                                                                                           | Every service package is named `app`; two in one process collide in `sys.modules`. Cost: one pytest start per service (CI matrix hides it).                                                                                                                                                                                                                                                                                                                                               |
| 2   | **Controller owns infra; workers only read URLs** (`env-or-container`): `TEST_PG_URL`/`TEST_REDIS_URL` if set (CI `services:` or `make deps-up`), else Testcontainers started once in the xdist controller                                                                                                                                                                                  | No N-containers-for-N-workers. Skipped for pure unit runs. FileLock is used only for cross-worker one-time work (login/token, seed), not for containers.                                                                                                                                                                                                                                                                                                                                  |
| 3   | **PG template DB → DB per worker → SAVEPOINT rollback per test**                                                                                                                                                                                                                                                                                                                            | Migrations once (real Alembic, so migration drift is tested), ~50 ms per worker DB, zero cleanup cost.                                                                                                                                                                                                                                                                                                                                                                                    |
| 4   | **Flows over concrete API adapters; Protocols only where there are ≥2 implementations or a test double**                                                                                                                                                                                                                                                                                    | `HttpTaskApi`/`HttpAuthApi` are concrete classes taking an `httpx.AsyncClient`; the client's transport (`ASGITransport` at component, network `base_url` at integration) is the swap point, so the same Flow runs on both layers. Protocols: `EventBus`/`EventReader` (fake vs aiokafka), `Cache` (real vs failing), `Clock` only if injected. No speculative ports.                                                                                                                      |
| 5   | **Component: real PG + Redis, Kafka replaced by** `RecordingEventBus`                                                                                                                                                                                                                                                                                                                       | Real Kafka costs 15–30 s startup and adds flake; Kafka behaviour is proven at integration. Events emitted are still schema-validated (contract).                                                                                                                                                                                                                                                                                                                                          |
| 6   | **Integration/UI reuse** `infra/docker-compose.yml` **(profile core)** + thin `infra/docker-compose.test.yml` override                                                                                                                                                                                                                                                                      | One stack definition. Override: expose api-gateway :8000 (bypass nginx limits), relaxed `nginx.test.conf`, WireMock, fixed ports.                                                                                                                                                                                                                                                                                                                                                         |
| 7   | **Integration/UI: unique data, no cleanup/reset**                                                                                                                                                                                                                                                                                                                                           | Parallel without locks; stack dies with the runner.                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 8   | **Sync Playwright** (pytest-playwright), UI tests are sync `def`                                                                                                                                                                                                                                                                                                                            | Official `pytest-playwright` is sync and xdist-friendly (a browser per worker process). The async API exists (`pytest-playwright-asyncio`) and works with pytest-asyncio, but pytest runs tests one at a time, so async gives no cross-test concurrency by itself. Mixing the *sync* API with a running event loop raises errors, so UI tests stay plain `def` and use sync httpx for data setup. Intra-test concurrency (`asyncio.gather`) is used in integration tests instead (§12.1). |
| 9   | **pytest-asyncio loop scope = session**                                                                                                                                                                                                                                                                                                                                                     | Session-scoped async engine/clients need one loop. (Deviation from "function" in notes; deliberate.)                                                                                                                                                                                                                                                                                                                                                                                      |
| 10  | **Polyfactory everywhere:** `ModelFactory` (Pydantic v2), `DataclassFactory`, `SQLAlchemyFactory`; `.build()` = no I/O, `create_async()` = async DB rows, `create_sync()` = sync seeding                                                                                                                                                                                                    | Native Pydantic v2/dataclass/SQLAlchemy support, typed `Factory[T]`, **real async persistence** (factory_boy has none), constraint-aware generated data, built-in Faker. Trade-off: random data can violate business rules, so override constrained fields; the fixture binds the session per test (§6.5). Replaces factory_boy.                                                                                                                                                          |
| 11  | **Consumer-side Pydantic models** in `saas_testkit/domain` (not imported from services)                                                                                                                                                                                                                                                                                                     | Black-box: DTO drift breaks tests (that is the point of contract testing). Only component/contract import service code (in-process app, DB models from `saas_shared.models`).                                                                                                                                                                                                                                                                                                             |
| 15  | **Src-layout package** `testing/src/saas_testkit` (not a loose `framework/` dir)                                                                                                                                                                                                                                                                                                            | Unique importable name (like `saas_shared`), installed editable by `uv sync`, no `sys.path` hacks, external-consumer import semantics, reusable by service unit tests in a separate prod-code-refactoring work. Tests/conftest stay outside the package.                                                                                                                                                                                                                                  |
| 12  | Python 3.14 in `testing/.python-version`; **if** `uv sync` **fails on a wheel (asyncpg, aiokafka, ddtrace, greenlet), drop to 3.13 for the venv** and keep syntax 3.14-clean                                                                                                                                                                                                                | Time-box: 15 min.                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| 16  | **Smoke ≠ synthetic.** `tests/smoke` = broad, shallow, post-deploy gate. `tests/synthetic` = narrow critical path run continuously with latency budgets and alerting. Same flows/adapters, different marker, schedule and failure policy. Grafana Cloud Synthetic Monitoring (k6-based, private probe for the local lab) is a complementary stretch, not a replacement for the Python suite | Python flows can't run inside Grafana SM (it runs k6 JS), so the Python synthetic suite stays as the SDET showcase.                                                                                                                                                                                                                                                                                                                                                                       |
| 14  | **Prod code is read-only by default; small** `testability:` **commits allowed** (extra `Depends()`, client factory, remove import-time side effect, `data-testid`) when overrides/patches would cost >30 min                                                                                                                                                                                | Owner-approved pragmatism. Behaviour changes/renames wait for a seaparate refactoring work so tests characterise today's behaviour. See `testing-modify-prod.mdc`.                                                                                                                                                                                                                                                                                                                        |
| 13  | Defects found → `xfail(strict=True, reason="BUG-n")` + `testing/KNOWN_ISSUES.md`                                                                                                                                                                                                                                                                                                            | Portfolio artefact: "framework found N real defects".                                                                                                                                                                                                                                                                                                                                                                                                                                     |




## 3. System under test — cheat sheet

(from ARCHITECTURE.md; code-level facts go to `SUT_MAP.md`)


| Service                    | Kind                                       | Talks to                     | Test-relevant facts                                                                                                                  |
| -------------------------- | ------------------------------------------ | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| nginx :80                  | proxy                                      | api-gateway                  | `/auth/` 5 req/min burst 3; API 10 req/s burst 20 per IP → **429 hazard for parallel tests**                                         |
| api-gateway :8000          | FastAPI                                    | auth, task, webhook-receiver | JWT HS256 required only for `/tasks/*`; strips Host/sentry-trace/baggage; CORS for :5173                                             |
| auth-service               | FastAPI + PG + Redis(db1)                  |                              | `POST /auth/token` (form), `GET /auth/me`; users admin/admin123, user/user123 (seed script, not automatic); user cache TTL 300       |
| task-service               | FastAPI + PG + Redis(db0) + Kafka producer |                              | `/tasks` CRUD, `PATCH /tasks/{id}/start                                                                                              |
| webhook-receiver           | FastAPI + Kafka producer                   |                              | `POST /webhooks/inbound` → topic `webhook_inbound`                                                                                   |
| webhook-dispatcher         | Kafka consumer (no HTTP; metrics :9100)    | `WEBHOOK_URL`                | consumes `task_created/updated`; POST with `Idempotency-Key`; backoff 1/2/4 s ±10 %; 4xx no retry; permanent failure → `webhook_dlq` |
| external-service-simulator | FastAPI                                    |                              | `/receive-webhook` (`fail_rate`,`delay`,`status`, idempotency dedupe), `/trigger-event` → gateway `/webhooks/inbound`                |
| notification-worker        | Kafka consumer                             | Toxiproxy → MailHog          | `task_created` → email (MIME text+html); MailHog API :8025                                                                           |
| scheduler-worker           | Celery + Beat                              | Redis(db2), Kafka, PG        | `retry_failed_webhooks` every 60 s (drain DLQ), `cleanup_old_tasks` every 5 m                                                        |
| Kafka envelope v1          |                                            |                              | `event_type, version, trace_id, timestamp, payload`; legacy raw JSON → `event_type="unknown"`                                        |
| frontend :5173             | React Kanban                               | gateway                      | drag-and-drop between columns, login page                                                                                            |




## 4. Pyramid and layer matrix

```
      smoke (post-deploy gate) / synthetic (continuous, prod)   few
          e2e_ui  (Playwright)
        integration (compose, network)
      component (service + real PG/Redis)                       many
    contract (OpenAPI / events / snapshots / Schemathesis)
  unit (pure code, mocker)                                      most
```


| Layer       | Process                               | PG                   | Redis  | Kafka               | External HTTP        | Isolation                                   | Parallel  | CI cadence                                                     |
| ----------- | ------------------------------------- | -------------------- | ------ | ------------------- | -------------------- | ------------------------------------------- | --------- | -------------------------------------------------------------- |
| unit        | –                                     | –                    | –      | –                   | –                    | process                                     | `-n auto` | every PR                                                       |
| contract    | in-proc                               | worker DB            | prefix | fake                | respx                | worker DB                                   | `-n auto` | PR (25–50 examples), nightly (500+, stateful)                  |
| component   | in-proc                               | worker DB + rollback | prefix | `RecordingEventBus` | respx                | rollback/test                               | `-n auto` | every PR                                                       |
| integration | containers                            | shared stack         | shared | real                | WireMock / simulator | unique data                                 | `-n 3`    | PR (fast subset), merge queue full                             |
| e2e_ui      | containers                            | shared stack         |        | real                |                      | context per test, unique data               | `-n 2`    | PR `-m critical`, merge full chromium, nightly cross-browser   |
| smoke       | target URL (fresh stack/staging/prod) | –                    | –      | –                   | –                    | smoke user, unique data                     | serial    | PR (against built stack) + after every deploy; blocks          |
| synthetic   | target URL (prod/staging)             | –                    | –      | –                   | –                    | dedicated synthetic user, `synthetic-` data | serial    | cron every 5 min (API), 30 min (browser); alerts, never blocks |




## 5. Repository layout

```
testing/
├── pyproject.toml            # ONE toml: package (hatchling, src/saas_testkit), deps, pytest, ruff (src=["src","tests"]), pyright, coverage
├── uv.lock  .python-version  testing.mk  README.md  KNOWN_ISSUES.md
├── conftest.py               # markers by path, --service, sys.path, controller infra, xdist hooks, failure links
├── compose.deps.yml          # optional: pg+redis for local runs (TEST_PG_URL / TEST_REDIS_URL)
├── contracts/                # committed snapshots: openapi/<svc>.json, events/*.schema.json
├── docs/                     # this file, plan, SUT_MAP.md
├── src/
│   └── saas_testkit/         # installable package (src-layout, hatchling, py.typed); `from saas_testkit.flows import ...`
│       ├── config/               # settings.py (pydantic-settings), services.py (name → path, module, port, DI seams)
│       ├── domain/               # Pydantic v2 boundary models: tasks, users, webhooks, events (Envelope v1, payloads), enums
│       ├── ports/                # Protocols ONLY for: EventBus, EventReader, Cache (+ Clock if injected). Everything else is a concrete adapter
│       ├── adapters/
│       │   ├── http/             # HttpTaskApi, HttpAuthApi (one client, injectable transport), retry/backoff policy
│       │   ├── kafka/            # AiokafkaReader (unique group), RecordingEventBus (in-memory)
│       │   ├── redis/            # RedisCache (namespaced)
│       │   ├── postgres/         # session helpers (sync + async)
│       │   ├── mail/             # MailHogInbox
│       │   ├── wiremock/         # WireMockSink (stubs + request journal)
│       │   ├── toxiproxy/        # ToxiproxyControl (latency/timeout/reset toxics)
│       │   └── playwright/       # pages/, components/
│       ├── factories/            # Polyfactory: payloads.py (ModelFactory), rows.py (SQLAlchemyFactory), events.py, builders.py, providers.py
│       ├── flows/                # task_lifecycle.py, auth.py, webhook_delivery.py, inbound_webhook.py (business language)
│       ├── infra/                # containers.py (env-or-container), template_db.py, app_loader.py, compose.py (up/wait/down/KEEP_STACK), xdist.py
│       ├── context.py            # RunContext(run_id, test_id), unique_title(), correlation/W3C traceparent
│       ├── polling.py            # eventually()
│       └── reporting.py          # on failure: print correlation id + Jaeger/Kibana search links
└── tests/
    ├── unit/                 # saas_testkit self-tests (factories, polling, envelope models, backoff helper)
    ├── contract/{http,events}/
    ├── component/{task_service,auth_service,api_gateway,webhook_receiver,external_service_simulator,webhook_dispatcher,notification_worker,scheduler_worker}/
    ├── integration/{services,scenarios}/
    ├── e2e_ui/task_lifecycle/
    ├── smoke/                # post-deploy gate
    └── synthetic/           # continuous critical-path checks (api/, browser/)
```

Plus `testing/synthetic/k6/critical_path.js` (non-Python asset for Grafana Synthetic Monitoring, stretch).
Every `tests/<layer>/` has its own `conftest.py` (fixtures for that layer only); root conftest has only cross-layer infra.

Service unit tests (later) live in `services/*/tests/unit` and reuse `saas_testkit.factories`; add the kit as a path dependency (`uv add --dev ../../testing`). Fixtures stay in `conftest.py`; if services' unit tests need them, extract a `saas_testkit.pytest_plugin` (entry point) then, not before.

## 6. Framework internals (skeletons — adapt, do not copy blindly)



### 6.1 Root conftest (infra in controller, path per service)

```python
# testing/conftest.py
def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--service", choices=sorted(SERVICES), default=None)

def pytest_configure(config: pytest.Config) -> None:
    if svc := config.getoption("--service"):                     # runs in controller AND workers
        sys.path[:0] = [str(REPO / "shared"), str(REPO / SERVICES[svc].path)]
    if not is_worker(config) and needs_infra(config):            # controller only
        config._infra = start_or_attach_infra()                  # env URLs or Testcontainers; builds template DB once

def pytest_configure_node(node) -> None:                         # xdist: controller -> worker
    node.workerinput["infra"] = node.config._infra.model_dump()

def pytest_unconfigure(config) -> None:
    stop_infra_if_owned(config)

def pytest_ignore_collect(collection_path, config) -> bool | None:   # skip other services' dirs
    ...
def pytest_collection_modifyitems(items) -> None:                # tests/<layer>/... -> marker
    ...
```

`needs_infra`: false when `INFRA=off`, or all args are under `tests/unit`, or `-m unit`. (Controller does not collect under xdist, so use args/markexpr, not item markers.)

### 6.2 Template DB, worker DB, rollback (async)

```python
@pytest.fixture(scope="session")
def worker_db(infra: Infra, worker_id: str) -> DbUrls:            # sync fixture; sync psycopg for DDL
    name = f"test_{infra.service}_{infra.layer}_{worker_id}"      # service + layer in the name: parallel runs share one PG safely
    with admin_engine(infra.pg_admin_url).connect() as c:         # AUTOCOMMIT
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        c.execute(text(f'CREATE DATABASE "{name}" TEMPLATE {infra.template_db}'))
    return DbUrls.for_database(infra.pg_admin_url, name)          # .async_url (asyncpg) / .sync_url

@pytest.fixture(scope="session")
async def engine(worker_db: DbUrls) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(worker_db.async_url)
    yield eng
    await eng.dispose()

@pytest.fixture
async def db(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        tx = await conn.begin()
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await tx.rollback()
```

Template: controller runs `alembic upgrade head` (repo `migrations/`, override DB URL via env — check `env.py` in SUT_MAP) into the template DB, then disposes all connections. **Template is built once and reused:** name = `app_template_<alembic head revision>`; controller takes `pg_advisory_lock(<const>)`, checks `pg_database` and builds it only if missing (concurrent per-service processes, local re-runs and `make deps-up` all reuse it; a new migration changes the head → new template, old ones are dropped by `make deps-clean`). Worker DBs are named `test_<service>_<layer>_<worker_id>` (layer = component|contract), dropped before create and at session end. `CREATE DATABASE ... TEMPLATE` requires no open connections to the template, so nobody connects to it. Fallback: `Base.metadata.create_all` from `saas_shared.models`. Add one test: single Alembic head + `alembic check` (no drift vs models).

Redis: `RedisCache(prefix=f"{worker_id}:{test_id}:")` or per-worker DB index; flush prefix at teardown. Services use fixed DB indexes 0/1, so override the service's redis dependency with the namespaced client.

### 6.3 Adapters (+ few ports) → flows → tests

```python
# ports/events.py — a real port: fake (component) vs aiokafka (integration)
class EventReader(Protocol):
    async def wait_for(self, topic: str, *, match: Callable[[Envelope], bool], timeout: float) -> Envelope: ...

# domain: ApiResponse[T] = frozen dataclass(status, data: T | None, error: ProblemBody | None, headers, elapsed)

# adapters/http/tasks.py — concrete class, no Protocol; any transport via the injected client
class HttpTaskApi:
    async def create(self, body: TaskCreate) -> ApiResponse[Task]: ...
    async def get(self, task_id: UUID) -> ApiResponse[Task]: ...
    def __init__(self, client: httpx.AsyncClient, ctx: RunContext) -> None: ...

# flows/task_lifecycle.py — business language; takes adapters/ports via DI
class TaskLifecycle:
    def __init__(self, tasks: HttpTaskApi, events: EventReader | None = None) -> None: ...
    async def new_task(self, **overrides) -> Task: ...          # asserts 201 + schema
    async def move_to_completed(self, task: Task) -> Task: ...
    async def task_created_event_published(self, task: Task) -> Envelope: ...   # uses eventually()

# test
async def test_completed_task_cannot_be_started_again(lifecycle: TaskLifecycle):
    task = await lifecycle.new_task()
    await lifecycle.move_to_completed(task)
    await lifecycle.expect_start_rejected(task, reason="invalid_transition")
```

Negative-path steps (`expect_*_rejected`) return/assert on `ApiResponse`; raw status access lives in flows, not tests.

### 6.4 Component client with dependency overrides (per service conftest)

```python
@pytest.fixture(scope="session")
def service_app(request) -> FastAPI:  return importlib.import_module("app.main").app   # path set by --service

@pytest.fixture
async def client(service_app, db, cache, event_bus) -> AsyncIterator[httpx.AsyncClient]:
    service_app.dependency_overrides[get_db] = lambda: db            # real names from SUT_MAP
    ...
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=service_app), base_url="http://test") as c:
        yield c
    service_app.dependency_overrides.clear()
```

If lifespan connects to Kafka/Redis at import/startup: swap the producer class/getter with `monkeypatch` **before** importing `app.main`; log it in SUT_MAP. If there is no DI seam, patch the module-level getter; if that costs >30 min, apply the `testability:` policy (ADR-14).

### 6.5 Factories (Polyfactory)

One factory family for all layers; the **method decides the layer behaviour**:


| Method                                                 | I/O                       | Used in                                                                                                                              |
| ------------------------------------------------------ | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `F.build(**kw)` / `F.batch(n)`                         | none, plain Python object | unit, contract, API payloads, event envelopes                                                                                        |
| `await F.create_async(**kw)` / `create_batch_async(n)` | async SQLAlchemy session  | component/contract rows (`SQLAlchemyFactory`)                                                                                        |
| `F.create_sync(**kw)`                                  | sync SQLAlchemy session   | sync contexts: one-time seed under FileLock (extra users, synthetic user), Playwright/integration/smoke setup against the stack's PG |


```python
from polyfactory import Use
from polyfactory.factories.pydantic_factory import ModelFactory
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory

class TaskCreateFactory(ModelFactory[TaskCreate]):      # Pydantic v2 DTO -> .build() only
    __model__ = TaskCreate
    title = Use(unique_title, "task")                   # constraints (min_length...) are respected automatically

class TaskRowFactory(SQLAlchemyFactory[Task]):          # ORM row from saas_shared.models
    __set_relationships__ = False                       # set explicitly (required by newer Polyfactory)
    status = Use(lambda: TaskStatus.CREATED)

# tests/component/conftest.py — bind the factories to THIS test's session without global state
@pytest.fixture
def rows(db: AsyncSession) -> Rows:
    class BoundTask(TaskRowFactory):
        __async_session__ = db                          # a session or a zero-arg callable
    class BoundUser(UserRowFactory):
        __async_session__ = db
    return Rows(task=BoundTask, user=BoundUser)

task = await rows.task.create_async(status=TaskStatus.COMPLETED)     # persisted inside the test's SAVEPOINT
```

Notes: (1) Polyfactory's SQLAlchemy persistence commits by default (flush is configurable); with `join_transaction_mode="create_savepoint"` a commit only releases the savepoint, the outer rollback still wipes it. (2) Bind per test via a subclass in a fixture; do not mutate a shared class attribute or rely on a `ContextVar` (async fixtures and tests may run in different contexts). (3) Reproducibility: `Factory.seed_random(run_seed)` in the root conftest; `RunContext.seed` is printed in the failure report. (4) Random data may violate business rules: override constrained fields (status, FKs, unique titles) explicitly. (5) Faker is bundled (`Factory.__faker__`); custom providers in `factories/providers.py` (`unique_title`, `jwt_claims`). (6) `UserRow.password_hash` = one cached argon2 hash. (7) Event factories (`ModelFactory[Envelope[TaskCreatedPayload]]`) build envelopes; a Builder only for `Envelope`/webhook bodies with many optional parts. Internal trusted dataclasses use `DataclassFactory`.

### 6.6 Polling, correlation, resilience helpers

- `eventually(fn, *, timeout=10, interval=0.2, message)` — retries on `AssertionError`/`None`, raises with last error and elapsed.
- `RunContext.run_id` (per session), `test_id` (per test). HTTP adapter adds `X-Request-ID` + W3C `traceparent` per test; `reporting.py` prints those plus Jaeger (`:16686`) / Kibana (`:5601`) search URLs in the failure report.
- Retry/backoff/circuit-breaker patterns are **tested**, not implemented in the kit: patch `asyncio.sleep` + `random.uniform`, assert sequence 1/2/4 s ±10 %. The kit's own HTTP adapter has a small retry policy only for GET/idempotent calls against a starting stack (tenacity, max 3, exponential).



### 6.7 Integration infra

- `saas_testkit/infra/compose.py`: `base_url` fixture pattern from the source doc: `BASE_URL` env (CI already up) else `docker compose -f infra/docker-compose.yml -f infra/docker-compose.test.yml --profile core up -d --wait` in the controller; `KEEP_STACK=1` keeps it up; `down -v` otherwise.
- Seed once per run under FileLock (`scripts/seed_dev.py` or direct idempotent SQL). Login once per worker → cached tokens (`admin_token`, `user_token`), and Playwright `storage_state`.
- `docker-compose.test.yml`: publishes api-gateway `:8000`, mounts `nginx.test.conf` (relaxed limits), adds `wiremock` on `:8089` and sets `webhook-dispatcher` `WEBHOOK_URL` to `http://wiremock:8080/hook`; keep `MAX_RETRIES`/backoff env if configurable to shorten runs. Nginx behaviour is tested by a few dedicated tests against `:80` only.



## 7. Test catalogue (scope for "cover the functionality")

Characterise first; record surprises in `KNOWN_ISSUES.md`.

**task-service (component, deepest):** create (201, schema, `status=created`, `task.created` envelope emitted & schema-valid); validation (empty/oversize/wrong-type title → 422); get 200/404/bad-uuid 422; list ordering by `created_at`, filter/pagination if present; state machine: created→in_progress→completed, and 409 for every illegal transition (parametrized matrix), 404 unknown id; `task.updated` event on each transition; cache: 2nd `GET` served from Redis (key + TTL asserted), invalidated on create/transition; Redis down → falls through to DB; Kafka publish failure → characterised behaviour; DB error → 5xx shape; race: N concurrent `start` on one task → exactly one success; health/ready/metrics.
**auth-service:** token OK for both roles, JWT claims/exp; wrong password / unknown user → 401 (same body); missing fields 422; `/me`: valid, expired, tampered signature, `alg=none`, missing/malformed header; password never leaked, hash is argon2; user cache hit on 2nd login; Redis down OK; `/ready` false when DB unavailable.
**api-gateway (respx upstreams):** routing per prefix; JWT required for `/tasks`* only (401 missing/invalid/expired); header stripping/forwarding; upstream 5xx passthrough, timeout and connection error mapping; CORS preflight for `localhost:5173`; health/metrics.
**webhook-receiver:** valid inbound → published envelope `webhook.inbound`; invalid body 422; producer failure → 5xx; correlation id propagation.
**external-service-simulator:** `fail_rate` 0/1, `status`, `delay` (sleep patched), idempotency dedupe (same key twice → `duplicate`; failed attempt not recorded), `/trigger-event` posts to gateway URL (respx) with retry.
**webhook-dispatcher (worker component; fake consumer/producer, respx):** envelope decode; `Idempotency-Key = payload.id`; 2xx success; 5xx/network → retries with backoff 1/2/4 ±10 % up to `MAX_RETRIES`; 4xx → no retry; exhausted → DLQ envelope `webhook.dlq`; legacy raw JSON handled; poison message skipped.
**notification-worker:** MIME multipart (text+html) contains task title; SMTP failure handling; legacy message.
**scheduler-worker:** `cleanup_old_tasks` on real PG (only `completed` older than N h; boundary; `0` disables; in_progress untouched); `retry_failed_webhooks` (DLQ message → HTTP replay via respx; offsets committed regardless; envelope + legacy).
**contract/http:** per service — OpenAPI valid; committed snapshot diff (removed/changed fields = fail, additive = ok); Schemathesis (25–50 examples PR, 500+ nightly, `not_a_server_error` + schema conformance); consumer-side Pydantic models validate real responses.
**contract/events:** Envelope v1 model; payload schema per topic (`task_created`, `task_updated`, `webhook_inbound`, `webhook_dlq`); JSON-schema snapshots in `contracts/events`; producers' captured events validate; legacy → `unknown`.
**integration/services:** every service `/health` through gateway; auth→gateway→task with real JWT; nginx `429` on auth burst and forwarded headers (dedicated, serial); `/metrics` exposes expected series after traffic.
**integration/scenarios:** S1 task lifecycle with side effects (Kafka `task_created` w/ envelope → MailHog email with unique title → WireMock got webhook with `Idempotency-Key`; transitions → `task_updated`); S2 webhook failure → retries (WireMock scenario 503,503,200) → success, and permanent failure → DLQ message → scheduler replay (`slow`); S3 inbound path simulator→gateway→receiver→`webhook_inbound`; S4 idempotent duplicate delivery; S5 resilience (`chaos`, nightly): Toxiproxy latency/reset on SMTP → API stays healthy, mail arrives after toxic removed; Redis paused → API still works.
**e2e_ui:** login success/failure (no storage_state); unauthenticated redirect; board shows own task; create task via UI (card in first column); drag to In Progress persists after reload (verified via API); drag to Completed; smoke subset = login + create + move.
**smoke (post-deploy gate, 1–2 min, broad):** `/health` of every service through the gateway, login for both roles, create + read one task, `/metrics` reachable, frontend returns 200. Reads `SMOKE_BASE_URL`; any failure blocks the pipeline/rollback.
**synthetic (continuous, narrow, API-first):** `api/`: gateway health → login (synthetic user) → create task → read → start → complete, with per-step latency budgets (soft warn, hard fail); `browser/` (optional, every 30 min): UI login → create card → move. Requirements: dedicated synthetic user, `X-Synthetic: true` header, titles prefixed `synthetic-` (scheduler cleanup removes completed), non-destructive, respects nginx limits, no secrets in logs, fail only after 3 consecutive failures (alert on the streak, not on one blip), JUnit + step-level timings in job summary. Reads `SYNTHETIC_BASE_URL`.

## 8. Security testing

- Static in CI: `ruff` (with `S` bandit rules), `bandit -r`, `pip-audit`/`uv pip audit`, `gitleaks` (free GitGuardian alternative), Trivy image scan (nightly).
- Functional (in the suites above): authN/authZ matrix, JWT tampering/expiry/`alg=none`, brute-force limit at nginx, injection-like strings in fields via Schemathesis, no secrets/hashes in responses or logs.
- Nightly stretch: OWASP ZAP baseline against the compose stack.



## 9. CI/CD (GitHub Actions) — adapted from the source DAG

```
push/PR ─┬─ lint (ruff, pyright)          ─┐
         ├─ security (bandit, audit, gitleaks)│
         ├─ unit (xdist, cov)              ─┼─► component-contract (matrix: service; PG+Redis services) ─┐
         └─ build-stack (buildx gha cache) ─────────────────────────────────────────────────────────────┼─► integration ─┐
                                                                                                         └─► ui-e2e       ├─► ci-gate (only required check)
```

- `concurrency: cancel-in-progress`; cheap jobs block expensive ones (`needs`).
- Env-driven: component job sets `TEST_PG_URL`, `TEST_REDIS_URL`, `SCHEMA_EXAMPLES`; integration/ui set `BASE_URL`. Same pytest command as local.
- Integration/UI: `docker compose ... up -d --wait` (buildx layer cache via `docker/bake-action` or `--build` with gha cache), `pytest -n 3`; on failure upload `docker compose logs`, Playwright `test-results/` (traces, screenshots), JUnit.
- Cadence: **PR** lint/security/unit/component/contract(light)/integration(fast subset)/UI `-m critical`; **merge_group** everything except deep fuzz + cross-browser; **nightly** Schemathesis deep+stateful, firefox/webkit, `chaos` + `slow` markers, flaky report (`--count 5` on tests with reruns), refresh `.test_durations`; `smoke.yml` after build/deploy against `SMOKE_BASE_URL` (blocks); `synthetic.yml` is written with `cron */5` (API) / `*/30` (browser) against `SYNTHETIC_BASE_URL` and an issue after 3 consecutive failures, but ships **dormant (`**workflow_dispatch` **only)**: GitHub runners and Grafana's public probes can't reach a local lab, and a tunnel would expose `admin/admin123`. Enable the cron only when a reachable URL exists (GitHub cron is best-effort anyway). For the local lab: `make synthetic-local` (loop every 5 min) and/or the Grafana private probe (§9.1, outbound-only, no tunnel).
- Reports: JUnit XML per job → `$GITHUB_STEP_SUMMARY` (dorny/test-reporter); coverage per service combined in a `coverage` job (`coverage combine`, fail-under 80 on service code touched by component+unit); reruns are listed, not hidden.
- "Trace coverage" is not a standard metric: replaced by **API coverage** (httpx event hook logs `method + route template`; a meta-test compares against each service's OpenAPI operations, reported as %).
- Sharding (`pytest-split --splits N --group k`) is wired in the matrix from day one with `shards: [1]`; raise it only when integration+UI exceeds ~8 min (see §12).
- Deploy step: intentionally out of scope for the lab (no target server); `smoke.yml` and `synthetic.yml` run against any URL.



### 9.1 Grafana Cloud Synthetic Monitoring (optional, stretch)

Free plan includes 100k synthetic executions/month (verify current limits on the pricing page). One check every 5 min from one location ≈ 8.6k executions/month; each extra probe location multiplies it. Checks are k6-based (HTTP/multi-step/browser scripts in JS), so they are a **separate JS copy** of the critical path, not the Python flows. The lab runs locally, so use a **private probe** (Grafana's Synthetic Monitoring Agent in a container, outbound-only, no public exposure) or a tunnel for public probes. Keep the script in `testing/synthetic/k6/critical_path.js` (reuse helpers from `load-tests/lib/helpers.js`), add alert rules and a dashboard. This is the **recommended continuous monitor for the local lab**. Interview value: continuous black-box SLI/SLO view next to the Python suite.

## 10. Flake and quality policy

`--strict-markers`, `pytest-randomly`, `pytest-timeout` (component 30 s, integration 120 s), `--reruns 1` only for `integration`/`e2e_ui` and always reported; web-first assertions; no sleeps; every `xfail` is strict and linked to `KNOWN_ISSUES.md`. New tests must pass 3× with random order and `-n auto`.

## 11. Risks and time-boxed fallbacks


| Risk                                                                          | Fallback (decide within 30 min)                                                                                                                                    |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Python 3.14 wheels missing                                                    | venv on 3.13                                                                                                                                                       |
| Service lifespan/import needs Kafka/Redis/Sentry/ddtrace                      | monkeypatch before import; `SENTRY_DSN` unset; stub `ddtrace` module in `sys.modules`                                                                              |
| No DI seam for DB/Redis in a service                                          | patch module-level getter/engine; else a minimal `testability:` commit adding a `Depends()` (ADR-14); else test at integration and note it                         |
| Schemathesis `from_asgi` runs app in a different event loop than the async DB | contract layer lets the app own its engine (env `DATABASE_URL` = worker DB, fake producer patched); still failing → `from_url(BASE_URL)` against the compose stack |
| Alembic `env.py` can't take a URL override                                    | `Base.metadata.create_all` for the template                                                                                                                        |
| Full-stack build too slow in CI                                               | build only `core` services needed; cache layers; run integration on merge queue + nightly, keep UI smoke on PR                                                     |
| Test env lacks service runtime deps, or services pin conflicting versions     | uv dependency group per service; sync only the group of the service under test (`uv sync --group <svc>`); long-term fix = R0 (uv + pyproject per service)          |
| Nginx limits / seeded data conflicts                                          | use gateway `:8000` from test override; assert only on own ids                                                                                                     |




## 12. Scaling model (for the interview and for hands-on experiments)

**Scale-up (vertical, inside one stack copy):** more xdist workers. component/contract `-n auto` (DB per worker from a shared template); integration `-n 3`; e2e_ui `-n 2` (browser per worker, context per test).
**Scale-out (horizontal, many stack copies):** CI matrix. component/contract: one job per service. integration/e2e_ui: `shard: [1..N]` with `pytest-split --splits N --group k --durations-path .test_durations`; **every shard brings up its own compose stack**, seeds it and logs in on its own; JUnit/coverage artifacts are merged in the gate job.
**Why scale-out needs no coordination:** all data is unique (uuid / run prefix), nothing is cleaned or reset, no shared mutable state between stacks, auth/seed is per stack.
**Limits of scale-up:** one stack's Kafka/PG/nginx and the runner's CPU/RAM (browsers are the heaviest). Hence conservative `-n` values for integration/UI.
**When to scale:** keep `shards: [1]` while integration+UI < ~8 min; first raise `-n` (cheap), then shards (more runners, more image builds, more minutes).
**Hands-on experiment (record the numbers in README):** run the integration suite with `-n 1`, `2`, `4` on the same stack and note wall time and failures; then two shards in CI (`shard: [1, 2]`) and compare. Expect sub-linear gains from `-n` (shared stack) and near-linear from shards (independent stacks, minus build/boot overhead). Refresh `.test_durations` nightly so shards stay balanced.