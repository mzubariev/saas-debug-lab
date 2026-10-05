# P0, P0.1, P0.2: recon, production prep, bootstrap

## P0: Recon (Agent mode). Result: `testing/docs/SUT_MAP.md`
Attach: the lab's README, `ARCHITECTURE.md`, `FILE_STRUCTURE.md` and `SERVICE_MAP.md` (all under `docs/system-architechture/`). No design documents from this pack are needed. The agent reads the code and runs it.

Task prompt:
Build `testing/docs/SUT_MAP.md` (about 150–400 lines, one table per service) for: api-gateway, auth-service, task-service, webhook-receiver, external-service-simulator, webhook-dispatcher, notification-worker, scheduler-worker, migrations and saas_shared. Derive every fact from the code, not from `ARCHITECTURE.md`, which is partly stale.
1. Read each service's entrypoint (`app.main:app`), its routes with request and response models (file paths), its auth requirements, its DI seams (DB session, Redis, Kafka producer, HTTP client, settings), its lifespan side effects, the Kafka topics and envelope helpers, how Alembic's `env.py` handles the database URL, the seed users, and the JWT secret and algorithm configuration. Also read `infra/nginx/nginx.conf` and record the exact rate-limit zones, their keys and burst settings.
2. Run the code. In a scratch venv install each service's requirements, import `app.main` with the environment from `.env.example`, call `/openapi.json` through `httpx.ASGITransport`, and import each worker's entry module. Record what fails and why, especially import-time side effects (Kafka or Redis connect, Sentry, OTel, ddtrace, metric registration).
3. For each service record: whether the database, Redis and Kafka URLs, `WEBHOOK_URL`, the JWT secret and the SMTP host are read only from the environment; which timings are hard-coded (retry and backoff, beat and cleanup intervals); which sync or async database and Kafka clients are used (note `psycopg2` and `kafka-python` in scheduler-worker); whether ddtrace runs at import; the real directory of each service (`services/core`, `services/external`, `workers`); the readiness mechanism of each worker (HTTP port, metrics port); and the Postgres major version used by `infra/docker-compose.yml`.
4. End with two lists: hazards, and candidates for production prep (small behaviour-neutral changes that would simplify the framework). Do not change any code.

Definition of done: `SUT_MAP.md` exists and you have skimmed it for wrong facts. A wrong line here is copied into every later task, so fix it immediately.

## P0.1: Production prep (small, behaviour-neutral seams)
Attach: `SUT_MAP.md` and `testing-modify-prod.mdc` (with `@`).

Goal: remove the obstacles the recon found before building the kit, so the framework stays simple and needs no monkeypatch hacks. Behaviour must stay identical. Make one commit per item with the prefix `testability:`. Run the manual lab smoke (login, create a task, move a task, see the email in MailHog, see the webhook delivered) before the first change and after the last. Keep every edit compatible with the Python 3.11 that the service images run.

Take only the items the recon proves are needed:
1. Remove Datadog (compose overlay, `ddtrace-run`, environment variables, docs). It blocks in-process imports. This is the only place where Datadog is removed.
2. Make every service and worker read its connections only from the environment: database URL, Redis URL including the DB index, Kafka bootstrap, `WEBHOOK_URL`, JWT secret and SMTP host. No hard-coded hosts remain.
3. Expose timing knobs through the environment, with the current values as defaults: the dispatcher's retries and backoff base, the scheduler's beat intervals (DLQ replay and cleanup) and the cleanup age threshold.
4. Remove import-time side effects. Sentry, OTel, metrics registration and Kafka connection happen in lifespan or startup code and stay inert when the environment is absent.
5. In compose, add a healthcheck for every service where one is possible (FastAPI services via `/health`), define an explicit service list for the test stack, and add a frontend `vite build` plus `preview` target. Workers have no HTTP app, so their readiness is checked through the metrics port, which the test kit handles.

Out of scope here: restructuring, and moving scheduler-worker to async SQLAlchemy and aiokafka (refactoring phase, see `p10-polish-after.md`).

Definition of done: the lab starts through `docker compose` as before, the manual smoke is green, and each change is its own commit.

Time-box: justify a production seam only when the test-side patch would cost more than 30 minutes.

## P0.2: Bootstrap
Attach: `design/arch-adr.md` and `design/arch-layers-layout.md`.

Steps:
1. Copy the files into the repository. Put `.cursor/rules/*.mdc` (the four rules) in place, keep the human documents in `testing/docs/`, place this pack in `testing/docs/cursor/` (with `design/`, `plan/` and `INDEX.md`), and add `SUT_MAP.md` from P0. Update `.cursorignore` as `00-workflow.md` describes. (Done.)
2. Create `testing/KNOWN_ISSUES.md` with three sections: "Defects" (BUG-n entries), "Testability changes" (production edits made under `testing-modify-prod.mdc`) and "Decisions since the plan" (one line per deviation from this plan).
3. Run this prompt:

Create the `testing/` skeleton described in `arch-layers-layout.md`: a src-layout package `src/saas_testkit/` (empty subpackages with `__init__.py` and `py.typed`) and a `conftest.py` in each `tests/<layer>/`. Create one `pyproject.toml` with: `[build-system]` using hatchling, `packages = ["src/saas_testkit"]`, `[tool.ruff] src = ["src", "tests"]`, and `[tool.uv] package = true`. Dependencies: pytest, pytest-asyncio, pytest-xdist, pytest-randomly, pytest-timeout, pytest-mock, pytest-cov, pytest-split, pytest-rerunfailures, pytest-playwright, httpx, respx, testcontainers[postgres,redis,kafka], sqlalchemy[asyncio]>=2.0,<2.2, asyncpg, psycopg[binary], alembic, redis, aiokafka, pydantic, pydantic-settings, polyfactory, schemathesis, openapi-spec-validator, tenacity, filelock, pyjwt, argon2-cffi, pytest-repeat, ruff, pyright and pip-audit. Configure `pythonpath`, `asyncio_mode=auto`, session loop scopes, `--strict-markers`, the markers, ruff including the `S` rules, pyright strict for `src/saas_testkit/`, and `[tool.coverage.run]` with `parallel = true`, `concurrency = ["thread", "greenlet"]` and `sigterm = true`. Also create `.python-version`, `testing/testing.mk` and a pre-commit configuration that runs `t-check`; include the `.mk` file from the root `Makefile`.

The targets in `testing.mk` are: `t-unit`; `t-component SERVICE=`; `t-component-all` (all services in parallel with `printf '%s\n' $(SERVICES) | xargs -P 4 -I{} $(MAKE) t-component SERVICE={}`, which needs `TEST_PG_URL`, `TEST_REDIS_URL` and `TEST_KAFKA_BOOTSTRAP` from `deps-up`); `deps-up` (starts Postgres with the test tuning and tmpfs from `arch-core-infra.md` section 6.2, Redis and Redpanda from `testing/compose.deps.yml`); `deps-clean` (drops stale templates and worker databases); `t-contract`; `contracts-update` (rewrites the committed snapshots, ADR-17); `t-int`; `t-ui`; `t-smoke`; `t-synthetic`; `t-lint`; `t-check` (ruff, pyright and a quick pytest); and `t-gate` (the final gate for a given layer or service: three runs, random order, `-n auto`).

Service runtime dependencies: component and contract tests import service code in-process, so the test environment must also contain each service's dependencies (fastapi, argon2, aiokafka, kafka-python, psycopg2, celery and so on). Put them in uv dependency groups per service (`[dependency-groups] task-service = [...]`), filled from that service's `requirements.txt` but without `ddtrace`, which P0.1 removed. Use `uv sync --group <svc>` or `--all-groups`. If versions conflict between services, install one group per session; this is what `--service` is for. After R0 the groups are replaced by the services' own packages.

Minimal CI right after bootstrap: `.github/workflows/ci.yml` with `lint` and `unit` only; P5 and P9 extend it.

Definition of done: `cd testing && uv sync && uv run pytest tests/unit -q` (one dummy test) and `uv run ruff check . && uv run pyright` pass.

Time-box: if `uv sync` fails on a wheel, apply the fallback from ADR-12 (venv on Python 3.13) after 15 minutes. As of October 2026 this is unlikely.
