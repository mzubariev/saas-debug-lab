# Testing architecture: framework core (root conftest, template DB, component app, helpers)
Used by P1. Every identifier inside the code skeletons below is illustrative. Anything marked `PLACEHOLDER`, `<SHA>`, `<pinned-version>` or described as "from SUT_MAP" must be replaced with a real value before use.

## 6.1 Root conftest (infra in controller, path per service)
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
needs_infra: true only when `--service` is set or `INFRA=on`. It is never true for `integration`, `e2e_ui`, `smoke`, or `synthetic`, even if one of those switches is set.

## 6.2 Template DB, worker DB, real commits (async)
```python
@pytest.fixture(scope="session")
def worker_db(infra: Infra, worker_id: str) -> DbUrls:            # sync fixture; sync psycopg for DDL
    name = f"test_{infra.service}_{infra.layer}_{worker_id}".replace("-", "_")  # hyphens become underscores
    with admin_engine(infra.pg_admin_url).connect() as c:         # AUTOCOMMIT
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        c.execute(text(f'CREATE DATABASE "{name}" TEMPLATE {infra.template_db}'))
    return DbUrls.for_database(infra.pg_admin_url, name)          # .async_url (asyncpg) / .sync_url

@pytest.fixture(scope="session")
async def session_maker(worker_db: DbUrls) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(worker_db.async_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()

@pytest.fixture
async def db(session_maker) -> AsyncIterator[AsyncSession]:       # plain session for arrange/assert; commits are real
    async with session_maker() as session:
        yield session

@pytest.fixture(scope="session")
def service_env(infra: Infra, worker_db: DbUrls, worker_id: str) -> Iterator[None]:
    mp = pytest.MonkeyPatch()                                     # set BEFORE the service is imported (Settings() and the engine are built at import)
    for key, value in worker_db.postgres_env().items():           # POSTGRES_HOST/PORT/DB/USER/PASSWORD: the services have no DATABASE_URL
        mp.setenv(key, value)
    mp.setenv("REDIS_URL", infra.redis_url_for(worker_index(worker_id)))   # auth/task; scheduler-worker reads CELERY_BROKER_URL / CELERY_RESULT_BACKEND instead
    mp.setenv("KAFKA_BOOTSTRAP_SERVERS", infra.kafka_bootstrap)
    mp.setenv("SERVICE_NAME", infra.service)                      # task-service Settings requires it and has no default
    mp.setenv("OTLP_ENDPOINT", "")                                # empty = no OTLP exporter; otherwise import starts a thread dialling otel-collector:4317
    mp.setenv("SENTRY_DSN", "")                                   # empty = Sentry stays inert
    yield
    mp.undo()

@pytest.fixture(autouse=True)
async def flush_redis(infra, worker_id) -> None:                  # cheap: FLUSHDB of this worker's DB index, before each test
    ...

@pytest.fixture
async def clean_db(session_maker) -> None:                        # via @pytest.mark.clean_db, runs BEFORE the test body
    async with session_maker() as s:
        tables = (await s.execute(text("DELETE FROM _touched RETURNING tbl"))).scalars().all()
        if tables:
            await s.execute(text(f"TRUNCATE {', '.join(quote_ident(t) for t in tables)} RESTART IDENTITY CASCADE"))
        await s.commit()
```
Template. The controller migrates `app_template_<head>_building` (cwd `migrations/`, because `script_location` is relative; Alembic requires `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, and `POSTGRES_HOST`, and `POSTGRES_PORT` defaults to 5432; it does not read `DATABASE_URL`), then renames that database to `app_template_<head>` after every connection to the scratch database is gone. A leftover `_building` database is dropped first. The controller takes `pg_advisory_lock`, checks `pg_database`, and builds only if the final name is missing (concurrent per-service sessions, local re-runs and `make deps-up` all reuse it; a new migration changes the head -> new template, old ones dropped by `make deps-clean`). Worker DBs are `test_<service>_<layer>_<worker_id>` with hyphens replaced by underscores (layer = component|contract), dropped before create and at session end. `CREATE DATABASE ... TEMPLATE` needs no open connections to the source, which is why the build uses the `_building` name.

Touched-table tracking (test-only DDL, only in the template, prod migrations untouched). Table _touched(tbl text primary key); function _mark() doing INSERT INTO _touched VALUES (TG_TABLE_NAME) ON CONFLICT DO NOTHING; statement-level AFTER INSERT OR UPDATE OR DELETE trigger on every table of schema public except alembic_version and _touched. Triggers see writes from the app, the scheduler and the tests alike (pg_stat_* counters are not reliable per test). clean_db truncates only tables touched since the last cleanup (TRUNCATE also empties indexes; CASCADE follows foreign keys), so cost is proportional to what a test used. Default = no cleanup (unique data); use clean_db only for tests asserting global state (e.g. scheduler cleanup). If a table is tiny, DELETE can beat TRUNCATE: measure before optimizing.

Redis. One Redis server per pytest session. `service_env` sets `REDIS_URL` from `redis_url_for(worker_index)` (`gw0` is DB 0) and `FLUSHDB` runs before every test (list/item caches are shared keys within a DB, so flush rather than namespace). `make t-component-all` runs services in parallel against one `TEST_REDIS_URL`, so auth and task share that server and the same worker indexes. The code has no per-service index offset. Keep `-n` <= 8 so indexes stay within the default 16.

Postgres tuning for tests (ADR-18). Start every test Postgres with `postgres -c fsync=off -c synchronous_commit=off -c full_page_writes=off -c max_connections=200`, data dir on tmpfs. max_connections: each worker holds its own app engine plus the test engine; default 100 runs out at -n 8 with several pools.
- Testcontainers (controller): PostgresContainer(image).with_command("postgres -c fsync=off -c synchronous_commit=off -c full_page_writes=off -c max_connections=200").with_tmpfs_mount(PGDATA_PARENT) (Testcontainers 4.x; verify the method name in the installed version).
- compose.deps.yml and the integration stack (docker-compose.test.yml override of postgres): command: postgres -c ... plus tmpfs: [<data dir>].
- GitHub Actions service container: command: + options: --tmpfs <data dir> (arch-ci.md §9.2). The lab runs Postgres 15, so use the same major everywhere (compose.deps.yml, Testcontainers, CI) with one pinned tag.
- Data dir by image: /var/lib/postgresql/data up to Postgres 17; Postgres 18+ keeps PGDATA under /var/lib/postgresql/<major>/docker, so mount tmpfs on /var/lib/postgresql. Pin the image tag and re-check on upgrade.
- RAM cost = template + one DB per worker + data: tens of MB here. Never use these flags outside throwaway test databases.

## 6.4 Component app and client (per service conftest)
```python
@pytest.fixture(scope="session")
async def service_app(service_env) -> AsyncIterator[FastAPI]:
    app = importlib.import_module("app.main").app                 # path from --service; env already set by service_env
    async with app.router.lifespan_context(app):                  # the app builds its own engine/redis/kafka from env
        yield app

@pytest.fixture
async def client(service_app) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=service_app), base_url="http://test") as c:
        yield c
```
The app talks to the worker DB, the worker's Redis DB index and Redpanda exactly as in prod, so no get_db/producer override is needed. Dependency failures are injected per test with mocker.patch.object(<adapter>, "<method>", autospec=True, side_effect=ConnectionError). dependency_overrides remain available (e.g. auth stubs) where a seam already exists and is simpler. If import/lifespan has blocking side effects, fix them in prod first (P0.1) instead of stubbing modules. No DI seam in a service: patch the module-level getter; if that costs >30 min, a minimal `testability:` commit adding Depends() (ADR-14), else test at integration level and note it.

## 6.6 Polling, correlation, resilience helpers
- eventually(fn, *, timeout=10, interval=0.2, message): retries on AssertionError/None, raises with last error and elapsed.
- RunContext.run_id (per session), test_id (per test). HTTP adapter adds X-Request-ID + W3C traceparent per test; reporting.py prints those plus Jaeger (:16686) / Kibana (:5601) search URLs in the failure report.
- Retry/backoff/circuit-breaker patterns are tested, not implemented in the kit: patch asyncio.sleep + random.uniform, assert the sequence (default: about 1 s then 2 s, each plus 0..+10 % jitter). The kit's own HTTP adapter has a small retry policy only for GET/idempotent calls against a starting stack (tenacity, max 3, exponential).
