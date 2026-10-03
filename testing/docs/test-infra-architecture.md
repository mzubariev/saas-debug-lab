# Test Infrastructure: pytest + Playwright + Testcontainers + Compose + GitHub Actions

Contents:

- **Part 1.** Architecture: isolation, resource sharing, parallelization, CI
- **Part 2.** Where to use Testcontainers and where to use Docker Compose

---

# Part 1. Test Infrastructure Architecture

## 0. Principles

1. **Goal:** for speed and resource efficiency, reuse the architecture, split into processes/workers inside each pytest run (for deep vertical scale-up), and distribute such instances across many shards/nodes/VMs (horizontal scale-out). For test isolation on shared resources, use db transactions/rollbacks per test and unique identifiers/names/namespaces for resources and data. Test suites are distributed with pytest-split by grouping tests based on execution time so that each group takes roughly the same amount of time.
2. **One heavy resource (Postgres, Redis) per CI job or shard, not per test and not per worker.** Isolation inside it is cheap: database-per-worker via `TEMPLATE`, transaction-per-test, unique data-per-test.
3. **The application image is built once per commit**, and all jobs only pull it.
4. **The higher the level in the pyramid, the fewer tests there are and the less often they run in full.** PRs run smoke tests, while the full suite runs in the merge queue and nightly.
5. **Cheap jobs block expensive ones** (`needs`). A failed lint or unit job should not start 4 e2e shards.
6. **One infrastructure startup mechanism.** Locally, pytest starts containers itself via Testcontainers. In CI, the same containers are started by compose or `services:`, while pytest only reads environment variables (`env-or-testcontainer`).

> Clarification from Part 2: a more accurate formulation is: **one mechanism per level**, and within each level pytest reads the address from an environment variable and, if it is absent, starts the resource itself.

---



## 1. What Each Level Needs


| Level                     | Application process                      | DB / broker                 | Browser         | Docker | Isolation                                                           |
| ------------------------- | ---------------------------------------- | --------------------------- | --------------- | ------ | ------------------------------------------------------------------- |
| **unit**                  | no                                       | no (fakes)                  | no              | no     | process level, `xdist -n auto`                                      |
| **component**             | in-process (ASGI + httpx)                | real Postgres (+Redis)      | no              | yes    | DB-per-worker from predefined&migrated TEMPLATE + rollback per test |
| **contract**              | in-process ASGI                          | Postgres, same as component | no              | yes    | same as component                                                   |
| **integration (API e2e)** | real container from the built image      | compose stack               | no              | yes    | stack per shard + unique data per test                              |
| **UI e2e**                | same container                           | same stack                  | sync Playwright | yes    | stack per shard + browser context per test                          |


External third-party services (payments, email) are replaced at the component level with `respx`, and in the e2e stack with WireMock or a mock container. Real external systems are not needed in automated tests.

---



## 2. CI DAG

```
                     push / PR
                         │
        ┌────────────────┼──────────────────┐
        ▼                ▼                  ▼
   ┌─────────┐      ┌─────────┐       ┌────────────┐
   │  lint   │      │  unit   │       │ build-image│  buildx + gha cache
   │ ruff    │      │ xdist   │       │ push ghcr  │  tag = sha
   │ pyright │      │ ~1 min  │       │ ~1-3 min   │
   └────┬────┘      └────┬────┘       └─────┬──────┘
        │                │                  │
        └───────┬────────┘                  │
                ▼                           │
        ┌───────────────────┐               │
        │ component+contract│ (image not needed, in-process)
        │ PG service + xdist│               │
        └────────┬──────────┘               │
                 └──────────┬───────────────┘
                            ▼   needs: [lint, unit, component, build-image]
              ┌─────────────┴─────────────┐
              ▼                           ▼
   ┌──────────────────────┐    ┌──────────────────────┐
   │ integration (API)    │    │ ui-e2e (Playwright)  │
   │ matrix shard 1..N    │    │ matrix shard 1..M    │
   │ own compose stack    │    │ own compose stack     │
   └──────────┬───────────┘    └──────────┬───────────┘
              └─────────────┬─────────────┘
                            ▼
                    ┌──────────────┐
                    │  ci-gate     │  the only required check
                    └──────────────┘
```

**Run frequency:**

```
PR:           lint, unit, component, contract (Schemathesis light: 25-50 examples),
              integration (full, if fast), UI smoke (@smoke, chromium)
merge queue:  everything above + UI full (chromium), Schemathesis medium
nightly:      UI cross-browser (firefox/webkit), Schemathesis deep + stateful,
              flaky analysis, repeated --count runs for suspicious tests
```

Cost trade-off: `needs` adds sequencing (+2-3 minutes to the total time), but on broken commits you do not pay for the most expensive jobs. For most teams, this is worthwhile.

---



## 3. Layout Inside a Single Shard (integration / UI e2e)

```
┌────────────────────── GitHub runner (ubuntu, 4 vCPU) ─────────────────────┐
│                                                                           │
│  docker compose up --wait   (app image from ghcr:sha, NO build on runner) │
│  ┌──────────┐   ┌────────┐   ┌────────┐   ┌───────────┐                   │
│  │ app :8000│──▶│postgres│   │ redis  │   │ wiremock  │ (external APIs)   │
│  │ (image)  │──▶│        │   │        │   │           │                   │
│  └────▲─────┘   └────────┘   └────────┘   └───────────┘                   │
│       │ HTTP                                                              │
│  ┌────┴───────────────────────────────────────────────────┐               │
│  │ pytest -n 3 (xdist)  --splits N --group k  (shard)     │               │
│  │  ├─ gw0: httpx / Playwright ─ browser (1 per worker)   │               │
│  │  ├─ gw1: ...            └─ context per test            │               │
│  │  └─ gw2: ...                                           │               │
│  │  Data isolation: tenant/org = uuid4 for EVERY test     │               │
│  │  Authentication: login once per worker → storage_state │               │
│  └────────────────────────────────────────────────────────┘               │
└───────────────────────────────────────────────────────────────────────────┘
```

**Why this way:**

- In e2e, the application is connected to one DB, so rollback is impossible, while DB-per-worker would require N application instances. The simplest and most reliable approach: **tests do not interfere with each other because they work in their own tenant or with their own UUID-based data**, and nothing needs to be cleaned up. The stack is discarded together with the runner.
- Parallelism has two levels: **shards (job matrix) scale horizontally, while xdist inside a shard scales vertically**. Per shard: 1 stack, 2-3 workers on 4 vCPU. For UI, more than 3 workers are usually unnecessary: Chromium is heavy (~300-500 MB per worker).
- Choose the number of shards based on the target duration: `shards ≈ total_run_time / (target_time − startup_overhead)`. Usually this is 2-4.

---



## 4. Isolation Layout for unit / component / contract

```
Controller (pytest main process, xdist)
  pytest_configure:
    ├─ if TEST_PG_URL is set (CI) → use it
    └─ otherwise Testcontainers: postgres:17-alpine (fsync=off, tmpfs)
        ├─ CREATE DATABASE app_template
        └─ alembic upgrade head            ← migrations ONCE
  pytest_configure_node → passes URL to workers

Worker gw0          Worker gw1          Worker gw2
  │                   │                   │
  CREATE DATABASE test_gw0 TEMPLATE app_template   ← ~50-100 ms, file copy
  │                   │                   │
  engine (session)    engine              engine
  │                   │                   │
  each test:  BEGIN → SAVEPOINT → test → ROLLBACK   (zero cleanup cost)
```

This way all workers use one container, while their data does not overlap. Migrations run once instead of N times, and rollback instead of cleanup takes fractions of a millisecond.

### Code: infrastructure (root conftest.py)

```python
# tests/conftest.py
import os, pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from testcontainers.postgres import PostgresContainer

_PG_ARGS = "postgres -c fsync=off -c synchronous_commit=off -c full_page_writes=off"

def _is_worker(config): return hasattr(config, "workerinput")

def pytest_configure(config):
    if _is_worker(config):
        return
    url = os.getenv("TEST_PG_URL")                      # CI: service is already running
    if not url and config.getoption("numprocesses", None) != 0 or not url:
        # locally: one container for the entire run, only for tests that need a DB
        pg = PostgresContainer("postgres:17-alpine").with_command(_PG_ARGS).with_kwargs(
            tmpfs={"/var/lib/postgresql/data": ""})
        pg.start()
        config._pg = pg
        url = pg.get_connection_url(driver="psycopg")
    _make_template(url)                                  # CREATE DATABASE app_template + alembic
    config._pg_url = url

def pytest_configure_node(node):                         # controller → worker
    node.workerinput["pg_url"] = node.config._pg_url

def pytest_unconfigure(config):
    if pg := getattr(config, "_pg", None):
        pg.stop()

@pytest.fixture(scope="session")
def worker_db_url(request, worker_id):
    base = (request.config.workerinput["pg_url"] if worker_id != "master"
            else request.config._pg_url)
    name = f"test_{worker_id}"
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        c.execute(text(f'CREATE DATABASE "{name}" TEMPLATE app_template'))
    return make_url(base).set(database=name).render_as_string(hide_password=False)
```

> It is better to start the container lazily, only if the selected test set contains tests marked `db`. A unit run should not wait for Docker.



### Code: rollback per test

```python
@pytest.fixture(scope="session")
def engine(worker_db_url):
    return create_engine(worker_db_url)

@pytest.fixture
def db(engine):
    conn = engine.connect()
    tx = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    yield session
    session.close(); tx.rollback(); conn.close()

@pytest.fixture
def client(db):                                          # component: application in-process
    app.dependency_overrides[get_session] = lambda: db
    transport = httpx.ASGITransport(app=app)
    with httpx.Client(transport=transport, base_url="http://t") as c:   # or AsyncClient
        yield c
    app.dependency_overrides.clear()
```

---



## 5. Contract Tests (OpenAPI + Pydantic v2 + Schemathesis)

```
app (Pydantic v2 models) ──▶ openapi.json (generated in the test)
                                   │
   ┌───────────────────────────────┼─────────────────────────────┐
   ▼                               ▼                             ▼
 1. Schema validity       2. Snapshot / breaking-change   3. Schemathesis
    openapi-spec-validator    diff against main (oasdiff)    fuzz + response validation
                                                             against the schema
```

```python
# tests/contract/test_api_contract.py
import schemathesis
from app.main import app

schema = schemathesis.openapi.from_asgi("/openapi.json", app)

@schema.parametrize()
@schemathesis.settings(max_examples=int(os.getenv("SCHEMA_EXAMPLES", 50)))
def test_api_conforms(case, client_with_db):
    case.call_and_validate()
```

Notes:

- Run Schemathesis in-process on **the same component stack** (real DB, external dependencies mocked). A separate container is not needed for this.
- PR: `SCHEMA_EXAMPLES=25-50`. Nightly: 500+ and stateful tests via links.
- Pydantic response models can also be used directly in integration tests: `Model.model_validate(resp.json())`. This validates the contract at virtually no additional cost.
- Perform breaking-change checks (comparing `openapi.json` with the version in main) as a separate fast step inside the component job.
- If Schemathesis responses require you to “suppress” 500 errors for obviously invalid inputs, it is better to fix validation than to filter out checks.

---



## 6. Playwright: How Not to Overpay

```python
# tests/e2e_ui/conftest.py
@pytest.fixture(scope="session")
def auth_state(browser_type, base_url, tmp_path_factory):   # login once per worker
    path = tmp_path_factory.mktemp("auth") / "state.json"
    b = browser_type.launch(); ctx = b.new_context(base_url=base_url)
    page = ctx.new_page(); do_login(page); ctx.storage_state(path=path); b.close()
    return path

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, auth_state):
    return {**browser_context_args, "storage_state": str(auth_state)}
```

- **One browser per worker, a new context per test.** A context is created in milliseconds and isolates cookies and storage.
- Authenticate **through the API** (or once through the UI) and reuse `storage_state`. Logging in through the form in every test is the most common waste of minutes.
- Create test data **through API fixtures**, not by clicking. A UI test should verify only what belongs to the UI.
- Settings: `--tracing retain-on-failure`, `--video off`, `--screenshot only-on-failure`. The trace is your primary debugging artifact.
- Cache browsers with `actions/cache` using the Playwright version as part of the key (`~/.cache/ms-playwright`), or use the ready-made `mcr.microsoft.com/playwright/python:vX` image as the job's `container:`. The second option is simpler, but the image is heavy. For PRs, Chromium is enough: `playwright install --with-deps chromium`.
- Fix flaky tests with explicit waits (web-first assertions `expect(...)`) and **not** with global retries. At most, use `--reruns 1` with reporting of the rerun so that flakiness remains visible.
- Markers: `@pytest.mark.smoke` runs on PRs, everything else in the merge queue and nightly.

---



## 7. GitHub Actions Skeleton

```yaml
name: ci
on:
  pull_request:
  merge_group:
  push: { branches: [main] }
  schedule: [{ cron: "0 2 * * *" }]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true          # saves the most

env:
  IMAGE: ghcr.io/${{ github.repository }}/app:${{ github.sha }}

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with: { enable-cache: true }
      - run: uv sync --frozen && uv run ruff check . && uv run ruff format --check . && uv run pyright

  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with: { enable-cache: true }
      - run: uv sync --frozen
      - run: uv run pytest tests/unit -n auto --cov --cov-report=xml

  build-image:
    runs-on: ubuntu-latest
    permissions: { packages: write, contents: read }
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with: { registry: ghcr.io, username: "${{ github.actor }}", password: "${{ secrets.GITHUB_TOKEN }}" }
      - uses: docker/build-push-action@v6
        with:
          push: true
          tags: ${{ env.IMAGE }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  component-contract:
    needs: [lint, unit]
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:17-alpine
        env: { POSTGRES_PASSWORD: test }
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U postgres" --health-interval 5s --health-retries 10
    env:
      TEST_PG_URL: postgresql+psycopg://postgres:test@localhost:5432/postgres
      SCHEMA_EXAMPLES: ${{ github.event_name == 'schedule' && '500' || '40' }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with: { enable-cache: true }
      - run: uv sync --frozen
      - run: uv run pytest tests/component tests/contract -n auto

  integration:
    needs: [lint, unit, component-contract, build-image]
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix: { shard: [1, 2] }
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with: { enable-cache: true }
      - run: uv sync --frozen
      - run: echo "${{ secrets.GITHUB_TOKEN }}" | docker login ghcr.io -u ${{ github.actor }} --password-stdin
      - run: docker compose -f compose.e2e.yml up -d --wait       # image: ${IMAGE}
      - run: uv run pytest tests/integration -n 3 --splits 2 --group ${{ matrix.shard }}
        env: { BASE_URL: http://localhost:8000 }
      - if: failure()
        run: docker compose -f compose.e2e.yml logs > compose.log
      - if: failure()
        uses: actions/upload-artifact@v4
        with: { name: "integration-${{ matrix.shard }}", path: compose.log }

  ui-e2e:
    needs: [lint, unit, component-contract, build-image]
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix: { shard: [1, 2, 3] }
    steps:
      # checkout, uv, docker login, compose up — same as in integration
      - uses: actions/cache@v4
        with:
          path: ~/.cache/ms-playwright
          key: pw-${{ hashFiles('uv.lock') }}
      - run: uv run playwright install --with-deps chromium
      - run: >
          uv run pytest tests/e2e_ui -n 3 --splits 3 --group ${{ matrix.shard }}
          ${{ github.event_name == 'pull_request' && '-m smoke' || '' }}
          --tracing retain-on-failure
      - if: failure()
        uses: actions/upload-artifact@v4
        with: { name: "traces-${{ matrix.shard }}", path: test-results/ }

  ci-gate:
    if: always()
    needs: [lint, unit, component-contract, integration, ui-e2e]
    runs-on: ubuntu-latest
    steps:
      - run: |
          echo '${{ toJSON(needs) }}' | jq -e 'all(.[]; .result == "success" or .result == "skipped")'
```

`compose.e2e.yml` contains `app` with `image: ${IMAGE}`, `postgres` (tmpfs, fsync=off), `redis`, `wiremock`, and a `healthcheck` for all of them so that `--wait` works. Migrations are run by an init container or in the entrypoint.

Shard splitting: `pytest-split` (with a `.test_durations` file updated nightly) or `pytest-xdist --dist loadfile`. The important thing is that shards are balanced by execution time, not by the number of tests.

---



## 8. Why This Design (Trade-offs)


| Decision                                                  | Alternative                    | Why this was chosen                                                                                      |
| --------------------------------------------------------- | ------------------------------ | -------------------------------------------------------------------------------------------------------- |
| `services:` + `TEST_PG_URL` in CI, Testcontainers locally | Testcontainers everywhere      | Faster and easier to debug in CI. Locally it works out of the box for developers without manual steps   |
| Compose for full-stack e2e                                | Testcontainers `DockerCompose` | The Compose file is both stack documentation and the local startup tool. One source of truth             |
| DB-per-worker via `TEMPLATE`                              | Schema per test / truncate     | Copying takes 50-100 ms, migrations run once, no races between workers                                  |
| Rollback at component level                               | Truncate / drop                | Cleanup cost is practically zero                                                                         |
| Unique data instead of cleanup in e2e                     | Reset DB between tests         | Parallelizes without locks and does not require a test-only API in production code                       |
| Build image once in GHCR                                  | Build in every job             | Saves minutes × number of shards                                                                         |
| Shards + xdist                                            | Only xdist on a large runner   | Small runners are cheaper and scale well                                                                 |
| `needs` for expensive jobs + `cancel-in-progress`         | Everything in parallel         | Savings mainly come from broken and outdated commits                                                     |
| Smoke on PR, full in merge queue / nightly                | Everything on every PR         | Fast feedback and controlled cost                                                                         |


---



## 9. What Not to Do

- A DB container **per test** or **per xdist worker** (N × startup time and memory).
- Session fixtures with Testcontainers without accounting for xdist: every worker will start its own container.
- Logging in through the UI in every test.
- One shared mutable seed dataset for all e2e tests, causing test order to affect results.
- `time.sleep` in Playwright and global `reruns=3`, which hide flaky tests.
- `docker compose build` on every shard.
- Separate clusters and infrastructure for every level until there is a proven need.
- Self-hosted runners and Kubernetes until the GitHub-minutes bill becomes a noticeable budget line. Optimize cache, `needs`, and shards first.

---



## 10. Implementation Order

1. Markers `unit/component/contract/integration/e2e/smoke`, directory structure `tests/<level>/`.
2. Unit + lint + `concurrency cancel` (day 1).
3. Infrastructure `conftest.py`: Postgres, template, rollback (component and contract).
4. Build the image in GHCR + `compose.e2e.yml` (integration).
5. Playwright: `storage_state`, API data fixtures, smoke on PRs.
6. Shards via `pytest-split`, update `.test_durations` nightly.
7. Nightly: Schemathesis deep, cross-browser, flaky-test report.

Exact numbers (number of shards and workers, memory limits) are chosen based on metrics from the first few weeks: job duration in Actions and peak Chromium memory usage.

---



# Part 2. Testcontainers or Docker Compose: What to Use Where



## Short Rule

- **Testcontainers**: when **pytest owns the resource** (1-2 containers that the test controls from code).
- **Docker Compose**: when you need to **start the whole system** (application from an image + DB + broker + mocks) and tests access it from the outside like a client.

Principle 5 from Part 1 (“one mechanism”) is more accurately understood as: **one mechanism per level**, while inside each level pytest reads the address from an environment variable and, if it is absent, starts the resource itself.

## Decision Flow

```
Does the test need the application process in a container?
│
├─ NO (app in-process: unit / component / contract)
│    Only DB/Redis dependencies are needed
│    └─▶ TESTCONTAINERS (locally)  |  services: or the same Testcontainers (CI)
│
└─ YES (app from image, tests act as an external client: integration / UI e2e)
     └─▶ DOCKER COMPOSE
           ├─ CI:        docker compose up -d --wait → pytest reads BASE_URL
           └─ locally:   make e2e-up (or a fixture that invokes compose)
```



## By Level


| Level               | What to use                               | Why                                                                                                                                                                                                                         |
| ------------------- | ----------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| unit                | nothing                                   | no infrastructure                                                                                                                                                                                                           |
| component, contract | **Testcontainers**                        | pytest should create the template DB itself, one DB per xdist worker, and change `fsync` and config. Dynamic ports, Ryuk cleans up containers after failures. A developer runs `pytest`, and everything works without setup |
| component in CI     | `services:` **or** the same Testcontainers | `services:` is easier to debug and slightly faster. Testcontainers also works on `ubuntu-latest` because Docker is available there. If you want one path, keep Testcontainers and pay 5-10 seconds                       |
| integration, UI e2e | **Compose**                               | a stack of 4-5 services with healthchecks and dependencies. One `compose.e2e.yml` serves as documentation, local startup, and CI                                                                                            |
| nightly, chaos      | Testcontainers (+ Toxiproxy)              | when the test needs to programmatically break the network, kill a container, or change configuration on the fly                                                                                                            |




## When to Choose Which

**Testcontainers, if:**

- the test or fixture controls the container lifecycle and configuration;
- dynamic ports and parallel independent instances are needed;
- guaranteed cleanup after failures is needed (Ryuk);
- there are one or two resources, and the application runs inside the pytest process.

**Compose, if:**

- the stack has multiple components and should match what people start manually;
- you need `depends_on: condition: service_healthy`, migration init containers, shared networks, and volumes;
- the application comes as a ready-made image from GHCR;
- the stack is needed not only by tests: for local development, demos, and manual QA.

**Avoid:**

- describing the same full stack in Python via Testcontainers: you will end up with a second “source of truth” next to the Compose file;
- starting Postgres through Compose for component tests: you lose per-worker DB flexibility and complicate local startup;
- using Testcontainers without accounting for xdist: containers should be started only in the controller process (as in `pytest_configure` above), otherwise every worker will start its own.



## “env or start it myself” Pattern

For e2e, use the same approach as for the DB: in CI the stack is already running, while locally a fixture starts it.

```python
# tests/integration/conftest.py
import os, subprocess, pytest

COMPOSE = ["docker", "compose", "-f", "compose.e2e.yml"]

@pytest.fixture(scope="session")
def base_url(request):
    if url := os.getenv("BASE_URL"):            # CI: stack is already started by a workflow step
        yield url
        return
    # locally: start it ourselves, once per session (controller), with --build
    if not hasattr(request.config, "workerinput"):
        subprocess.run([*COMPOSE, "up", "-d", "--wait", "--build"], check=True)
    yield "http://localhost:8000"
    if not hasattr(request.config, "workerinput") and not os.getenv("KEEP_STACK"):
        subprocess.run([*COMPOSE, "down", "-v"], check=True)
```

There is also a ready-made option: `ComposeContainer` from `testcontainers`. It does the same thing: starts the Compose file, waits for healthchecks, returns service addresses, and cleans up after itself. It is convenient if you want the fixture not to call `subprocess` manually. But internally it still invokes `docker compose`, so the gain is small.

Also add `KEEP_STACK=1` for developers: the stack remains running between runs, and rerunning a single test takes seconds.

## Final Picture

```
Locally:
  pytest tests/unit          → without Docker
  pytest tests/component     → Testcontainers starts Postgres (once)
  pytest tests/integration   → fixture invokes compose up --wait
  pytest tests/e2e_ui        → same + Playwright

CI:
  component-contract job     → services: postgres  (TEST_PG_URL)
  integration / ui-e2e jobs  → compose up --wait   (BASE_URL)
  pytest is the same everywhere; only environment variables change
```

Bottom line: use Testcontainers where pytest manages the resource, and Compose where you start the system as a whole.
