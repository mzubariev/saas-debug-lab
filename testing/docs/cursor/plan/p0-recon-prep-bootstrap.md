# P0, P0.1, P0.2 - recon, prod prep, bootstrap

## P0 - Recon (executable) -> SUT_MAP.md (Agent mode)
Attach: lab README, ARCHITECTURE, FILE_STRUCTURE (the 3 lab docs). Cursor reads the code and runs it.
Task: build testing/docs/SUT_MAP.md (~150-400 lines, one table per service) for: api-gateway, auth-service, task-service, webhook-receiver, external-service-simulator, webhook-dispatcher, notification-worker, scheduler-worker, migrations, saas_shared.
1. Read: entrypoint (app.main:app), routes + request/response models (file paths), auth requirements, DI seams (DB session, redis, kafka producer, http client, settings), lifespan side effects, Kafka topics + envelope helpers, Alembic env.py URL handling, seed users, JWT secret/alg config.
2. Run: in a scratch venv install each service's requirements, import app.main with env from .env.example, call /openapi.json through httpx.ASGITransport, import each worker's entry module. Record what fails and why (import-time side effects: Kafka/Redis connect, Sentry, OTel, ddtrace, metric registration).
3. Record per service: are DB/Redis/Kafka URLs, WEBHOOK_URL, JWT secret and SMTP host read only from env? Which timings are hard-coded (retry/backoff, beat and cleanup intervals)? Which sync/async DB and Kafka clients are used (note psycopg2/kafka-python in scheduler-worker)? Does ddtrace run at import?
4. End with two lists: hazards and PREP candidates (small behaviour-neutral prod changes that would simplify the framework). No code changes.
DoD: SUT_MAP.md exists; you skim it for wrong facts.

## P0.1 - Prod prep (small, behaviour-neutral seams)
Attach: SUT_MAP.md, testing-modify-prod.mdc.
Goal: remove obstacles the recon found before building the kit, so the framework stays simple (no monkeypatch hacks). Behaviour stays identical. One commit per item, prefix `testability:`. Run the manual lab smoke (login, create task, move task, email in MailHog, webhook delivered) before the first change and after the last.
Candidates (take only what the recon proves is needed):
1. Remove Datadog (compose overlay, ddtrace-run, env, docs): it blocks in-process imports and is planned anyway.
2. Every service/worker reads connections only from env (DB URL, Redis URL including DB index, Kafka bootstrap, WEBHOOK_URL, JWT secret, SMTP host); no hard-coded hosts.
3. Timing knobs via env, current values as defaults: dispatcher retries/backoff base, scheduler beat intervals (DLQ replay, cleanup), cleanup age threshold.
4. No import-time side effects: Sentry/OTel/metrics registration/Kafka connect happen in lifespan/startup; inert when env is absent.
5. Compose: a healthcheck for every service (/health) and an explicit service list for the test stack; frontend vite build + preview target.
Not now: restructuring, or moving scheduler-worker to async SQLAlchemy/aiokafka (refactoring phase, see p10).
DoD: the lab starts via docker compose as before; manual smoke green; each change is its own commit.
Time-box: a prod seam is justified when the test-side patch would cost >30 min.

## P0.2 - Bootstrap
Attach: arch-adr.md, arch-layers-layout.md (ADRs, repo layout).
1. Copy into repo: .cursor/rules/*.mdc (4 files), testing/docs/* (human docs), testing/docs/cursor/* (this pack), SUT_MAP.md from P0. Create .cursorignore. [DONE]
2. Prompt:
Create testing/ skeleton per arch-layers-layout.md: src-layout package src/saas_testkit/ (empty subpackages with __init__.py, py.typed), tests/<layer>/conftest.py; pyproject.toml with [build-system] hatchling, packages = ["src/saas_testkit"], [tool.ruff] src = ["src", "tests"], [tool.uv] package = true (deps: pytest, pytest-asyncio, pytest-xdist, pytest-randomly, pytest-timeout, pytest-mock, pytest-cov, pytest-split, pytest-rerunfailures, pytest-playwright, httpx, respx, testcontainers[postgres,redis,redpanda], sqlalchemy[asyncio], asyncpg, psycopg[binary], alembic, redis, aiokafka, pydantic, pydantic-settings, polyfactory, schemathesis, openapi-spec-validator, tenacity, filelock, pyjwt, argon2-cffi, pytest-repeat, ruff, pyright, pip-audit; pythonpath, asyncio_mode=auto, loop scopes = session, --strict-markers, markers, ruff incl. S, pyright strict for src/saas_testkit/), .python-version, testing/testing.mk (t-unit, t-component SERVICE=, t-component-all (all services in parallel: `printf '%s\n' $(SERVICES) | xargs -P 4 -I{} $(MAKE) t-component SERVICE={}`; needs TEST_PG_URL/TEST_REDIS_URL/TEST_KAFKA_BOOTSTRAP via deps-up, which starts Postgres (test tuning + tmpfs, arch-core-infra.md §6.2) + Redis + Redpanda from testing/compose.deps.yml), deps-clean (drop stale templates/worker DBs), t-contract, contracts-update (rewrite committed snapshots, ADR-17), t-int, t-ui, t-smoke, t-synthetic, t-lint, t-check = ruff + pyright + quick pytest, deps-up) and a pre-commit config running t-check, included from the root Makefile.
Service runtime deps: component/contract import service code in-process, so the test env must also contain each service's dependencies (fastapi, argon2, aiokafka, kafka-python, psycopg2, celery, ...). Put them in uv dependency groups per service ([dependency-groups] task-service = [...], filled from that service's requirements.txt) and use uv sync --group <svc> / --all-groups; if versions conflict between services, install one group per session (this is where --service helps). After R0 (uv in services) these groups are replaced by the services' own packages.
Minimal CI right after bootstrap: .github/workflows/ci.yml with lint + unit only (extended in P5 and P9).
DoD: `cd testing && uv sync && uv run pytest tests/unit -q` (one dummy test) and `uv run ruff check . && uv run pyright` pass.
Time-box: if uv sync fails on a wheel, apply ADR-12 (venv on 3.13) after 15 min.
