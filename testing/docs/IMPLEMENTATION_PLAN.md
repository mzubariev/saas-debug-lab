# Implementation Plan + How to work with Cursor

## A. Strategy: vertical slices, not "framework first"

1. Build the **thinnest foundation** (P0–P1), then prove it with **one end-to-end slice** (task-service create → get).
2. Grow the framework **only when a test needs it** (extract on the second use). Breadth per layer comes after the slice is green.
3. **CI goes green** (P5) with what exists, then only grows.
4. Order = risk first: infra hazards (xdist, template DB, app loading) are solved before writing 100 tests.

## B. Working with Cursor (token economy)

**Context strategy — do NOT feed the whole lab.**

- One-time recon (P0) turns the code into a ~150-400-line `SUT_MAP.md` (routes, DI seams, env vars, quirks). After that every task reads: rule (auto) + `SUT_MAP.md` + the one service file it touches.
- Rules auto-attach by glob: `python-style` (all `*.py`), `testing-core` (`testing/**`), `playwright` (UI dirs). You never paste rules. Attach `TESTING_ARCHITECTURE.md` only in P0–P2 and when a design question appears; otherwise paste just the task block from this file.
- Add `.cursorignore`: `frontend/node_modules`, `observability/`, `load-tests/`, `chaos/`, `docs/incidents-playbooks/`, `**/*.lock`, `.venv`, `infra/**/grafana`, `**/__pycache__`, `test-results/`. (Unignore `frontend/src` only for P7.)
- **One task = one new chat.** Name chats `P3.2 task-service component`. Commit after every green task (`git commit -m "P3.2 ..."`), so a bad chat is just `git restore`.
- **Models:** strong model in *Ask/Plan* mode for P1, P2, P6 design decisions (short); cheaper/auto model in *Agent* mode for mechanical test writing (P3, P4, P7). If a task fails twice, stop, `git restore`, restate the task narrower — do not let the chat grow.
- **Prompt discipline:** every prompt ends with the block:
`Output: no explanations. Run the DoD command. If it fails, fix up to 3 times, then stop and show the last 40 lines. Final report ≤ 10 lines.`
- Ask for **the pattern once, then reuse**: for P3, do task-service fully, review it yourself, then tell Cursor "replicate the structure of tests/component/task_service for auth-service" (cheap, consistent).
- Review what matters: conftest/fixtures/flows/ports. Skim generated tests; run them 3× random order.
- **Golden example, then replicate:** finish task-service, review it yourself, then "replicate `@tests/component/task_service` for auth-service".
- **Plan first on hard tasks:** P1, P2, P6 start in Plan/Ask mode (short plan, you approve), then Agent.
- **Free quality gate:** `make t-check` (ruff + pyright + quick pytest) plus a pre-commit hook running the same; Cursor runs `make t-check` as part of DoD.
- **Mutation spot-check:** per service, break one prod line or flip one assertion; a test must go red. Catches tautological AI tests.
- **Parallelise:** after the golden example P3.2–P3.6 are independent; use parallel agents/worktrees if available. Drop a chat after ~15 turns or 2 failed fixes (`git restore`, narrower prompt).
- Use terminal output tails (`| tail -40`), `-x -q`, `--lf` to keep loops cheap.

**Interview angle:** keep `KNOWN_ISSUES.md` (defects found), ADR table in the architecture doc, and README diagrams — they are the portfolio.

## C. Prompt template

```
You are Principal Software Development Engineer in Test (the main programming language is Python v3.14).
Task <id>: <title>.
Read only: testing/docs/SUT_MAP.md and <files>.
Follow the auto-attached rules.
Deliver: <list>.
DoD: <command(s)> pass; ruff + pyright clean.
Output: no explanations. Run the DoD command. If it fails, fix up to 3 times, then stop and show the last 40 lines. Final report ≤ 10 lines. Give me a name for a commit message to highlight what was done.
```



## D. Schedule

**Part 1 — foundation, component, contract, CI v1**  P0 → P5

**Part 2 — integration, UI, smoke + synthetic, CI v2, polish**  P6 → P10. Cut-line if behind (drop in this order): P10 polish → nightly/chaos scenarios → notification/scheduler component tests → cross-browser → API-coverage meta-test → Schemathesis stateful → sharding. (Within P8 cut P8.3 Grafana SM first.)

---



## P0 — Recon (executable) → `SUT_MAP.md` (Agent mode)

Attach: README, ARCHITECTURE, FILE_STRUCTURE (the 3 docs). Cursor reads the code **and runs it**.

> Task: build `testing/docs/SUT_MAP.md` (~150–400 lines, one table per service) for: api-gateway, auth-service, task-service, webhook-receiver, external-service-simulator, webhook-dispatcher, notification-worker, scheduler-worker, migrations, saas_shared.
>
> 1. Read: entrypoint (`app.main:app`), routes + request/response models (file paths), auth requirements, DI seams (DB session, redis, kafka producer, http client, settings), lifespan side effects, Kafka topics + envelope helpers, Alembic `env.py` URL handling, seed users, JWT secret/alg config.
> 2. **Run**: in a scratch venv install each service's requirements, import `app.main` with env from `.env.example`, call `/openapi.json` through `httpx.ASGITransport`, import each worker's entry module. Record what fails and why (import-time side effects: Kafka/Redis connect, Sentry, OTel, ddtrace, metric registration).
> 3. Record per service: are DB/Redis/Kafka URLs, `WEBHOOK_URL`, JWT secret and SMTP host read **only from env**? Which timings are hard-coded (retry/backoff, beat and cleanup intervals)? Which sync/async DB and Kafka clients are used (note `psycopg2`/`kafka-python` in scheduler-worker)? Does `ddtrace` run at import?
> 4. End with two lists: **hazards** and **PREP candidates** (small behaviour-neutral prod changes that would simplify the framework). No code changes.
>
> DoD: `SUT_MAP.md` exists; you skim it for wrong facts.

---



## P0.1 — Prod prep (small, behaviour-neutral seams)

Attach: `SUT_MAP.md`, `testing-modify-prod.mdc`.

Goal: remove the obstacles the recon found **before** building the kit, so the framework stays simple (no monkeypatch hacks). Behaviour must stay identical. One commit per item with the prefix `testability:`. Run the manual lab smoke before the first change and after the last (login, create task, move task, email in MailHog, webhook delivered).

Candidates (take only what the recon proves is needed):

1. Remove Datadog (compose overlay, `ddtrace-run`, env, docs): it blocks in-process imports and is planned anyway.
2. Every service/worker reads connections only from env (DB URL, Redis URL including DB index, Kafka bootstrap, `WEBHOOK_URL`, JWT secret, SMTP host); no hard-coded hosts.
3. Timing knobs via env with current values as defaults: dispatcher retries/backoff base, scheduler beat intervals (DLQ replay, cleanup), cleanup age threshold.
4. No import-time side effects: Sentry/OTel/metrics registration/Kafka connect happen in lifespan/startup; inert when env is absent.
5. Compose: a healthcheck for every service (`/health`) and an explicit service list for the test stack; frontend `vite build` + `preview` target.

Not now: restructuring, or moving scheduler-worker to async SQLAlchemy/aiokafka. That happens in the refactoring phase (section F) under the integration safety net.
DoD: the lab starts via `docker compose` as before; manual smoke is green; each change is its own commit.

---



## P0.2 — Bootstrap

Attach: `TESTING_ARCHITECTURE.md` §2, §5.

1. Copy files into repo: `.cursor/rules/*.mdc` (4 files), `testing/docs/*`, `SUT_MAP.md` from P0. Create `.cursorignore`. [DONE]
2. Prompt:

> Create `testing/` skeleton per §5: src-layout package `src/saas_testkit/` (empty subpackages with `__init__.py`, `py.typed`), `tests/<layer>/conftest.py`; `pyproject.toml` with `[build-system]` hatchling, `packages = ["src/saas_testkit"]`, `[tool.ruff] src = ["src", "tests"]`, `[tool.uv] package = true` (deps: pytest, pytest-asyncio, pytest-xdist, pytest-randomly, pytest-timeout, pytest-mock, pytest-cov, pytest-split, pytest-rerunfailures, pytest-playwright, httpx, respx, testcontainers[postgres,redis,redpanda], sqlalchemy[asyncio], asyncpg, psycopg[binary], alembic, redis, aiokafka, pydantic, pydantic-settings, polyfactory, schemathesis, openapi-spec-validator, tenacity, filelock, pyjwt, argon2-cffi, pytest-repeat, ruff, pyright, pip-audit; `pythonpath`, `asyncio_mode=auto`, loop scopes = session, `--strict-markers`, markers, ruff incl. `S`, pyright strict for `src/saas_testkit/`), `.python-version`, `testing/testing.mk` (`t-unit`, `t-component SERVICE=`, `t-component-all` (all services in parallel: `printf '%s\n' $(SERVICES) | xargs -P 4 -I{} $(MAKE) t-component SERVICE={}`; needs `TEST_PG_URL`/`TEST_REDIS_URL`/`TEST_KAFKA_BOOTSTRAP` via `deps-up`, which starts Postgres (test tuning + tmpfs, architecture §6.2) + Redis + Redpanda from `testing/compose.deps.yml`), `deps-clean` (drop stale templates/worker DBs), `t-contract`, `t-int`, `t-ui`, `t-smoke`, `t-synthetic`, `t-lint`, `t-check` = ruff + pyright + quick pytest, `deps-up`) and a pre-commit config running `t-check` included from the root Makefile.
> Service runtime deps: component/contract import service code in-process, so the test env must also contain each service's dependencies (fastapi, argon2, aiokafka, kafka-python, psycopg2, celery, ...). Put them in uv dependency groups per service (`[dependency-groups] task-service = [...]`, filled from that service's `requirements.txt`) and use `uv sync --group <svc>` / `--all-groups`; if versions conflict between services, install one group per session (this is where `--service` helps). After R0 (uv in services) these groups are replaced by the services' own packages.
> Minimal CI right after bootstrap: `.github/workflows/ci.yml` with `lint` + `unit` only (extended in P5 and P9).
> DoD: `cd testing && uv sync && uv run pytest tests/unit -q` (one dummy test) and `uv run ruff check . && uv run pyright` pass. If `uv sync` fails on a wheel, apply ADR-12.



## P1 — Infra core + first slice — strongest model

Attach: `TESTING_ARCHITECTURE.md` §2, §6, `SUT_MAP.md`.

1. `src/saas_testkit/config` (`settings.py`, `services.py`), `context.py`, `polling.py`, `infra/{containers,template_db,app_loader,xdist}.py` (Testcontainers Postgres with the ADR-18 flags + tmpfs), root `conftest.py` (markers by path, `--service`, controller infra, `pytest_configure_node`, `needs_infra`, ignore other services), `tests/component/conftest.py` (`worker_db`, `session_maker`, `db`, `service_env`, `flush_redis`, `clean_db`, Redpanda/`KafkaEventReader`), template DB with touched-table tracking (architecture §6.2).
2. Domain models for tasks/users/envelope, concrete `HttpTaskApi`, `TaskLifecycle` flow, `TaskCreateFactory` (Polyfactory `ModelFactory`), `TaskRowFactory` (`SQLAlchemyFactory`) and the `rows` fixture binding row factories to the test session (`create_async`).
3. `tests/component/task_service/conftest.py` (`service_app` with lifespan, `client`; no `get_db` override: the app builds its engine from env) + **two tests**: `create_task_returns_created_status`, `unknown_task_returns_404`.
4. `tests/unit` self-tests: `eventually`, `unique_title`, factories.

DoD: `make t-component SERVICE=task-service` passes with `-n 0` and `-n 3`, 3× in a row, DB-per-worker visible (`test_task_service_component_gw0`, `..._gw1`); second run reuses the template (no Alembic re-run, check log); `pytest tests/unit` needs no Docker (`docker stop` all, still green); ruff + pyright clean.
Review yourself carefully: this is the heart of the kit.

## P2 — Adapters, factories, flows for the rest

Attach: rule, `SUT_MAP.md`, `TESTING_ARCHITECTURE.md` §6.3, §6.5.

> Add concrete `HttpAuthApi` (no Protocol), `KafkaEventReader` (concrete, real Redpanda/Kafka), `Envelope`/payload models for `task_created`, `task_updated`, `webhook_inbound`, `webhook_dlq`, JWT factory (valid/expired/tampered/alg-none), `UserRowFactory` (cached argon2 hash), `auth` flow, `WebhookDelivery` flow skeleton.
> DoD: unit self-tests for factories/models green; pyright clean.



## P3 — Component tests — do task-service fully first

Each sub-task = new chat. Attach: rule, SUT_MAP, the service's route/deps files, and the catalogue line from `TESTING_ARCHITECTURE.md` §7.

- **P3.1 task-service:** full catalogue list. Bugs → `xfail(strict)` + `KNOWN_ISSUES.md`.
- **P3.2 auth-service:** replicate structure of P3.1.
- **P3.3 api-gateway:** respx upstreams, JWT matrix.
- **P3.4 webhook-receiver + external-service-simulator.**
- **P3.5 webhook-dispatcher + notification-worker:** worker components; patch `asyncio.sleep`/jitter. Coupled to internal functions: do it after the worker refactor (section F) or cover the behaviour black-box in integration (S1–S4) first.
- **P3.6 scheduler-worker:** real PG for cleanup (`clean_db`); respx for replay. Same note: do it after the scheduler refactor, cover cleanup and DLQ replay in integration with the shortened timing knobs meanwhile.
DoD each: `make t-component SERVICE=<x>` green ×3 random order, `-n auto`; coverage of the service's routes/services printed (`--cov=<service path>`).



## P4 — Contract tests

Attach: rule, SUT_MAP, `TESTING_ARCHITECTURE.md` §7 (contract lines) + §7.1 (contract principles) + §11 (Schemathesis fallback).

- P4.1 `contract/events`: Envelope + payload schema tests, JSON-schema snapshots, legacy → `unknown`, producers' captured events validate (captured through `KafkaEventReader` on Redpanda).
- P4.2 `contract/http`: OpenAPI validity, exact committed snapshots (ADR-17, `make contracts-update` for explicit updates), Schemathesis per service (`SCHEMA_EXAMPLES` env; a 500 is never filtered away: `xfail(strict)` + `KNOWN_ISSUES.md`), consumer-side `model_validate` of real responses (§7.1).
DoD: `make t-contract SERVICE=<x>` green for task, auth, webhook-receiver, simulator, gateway. If Schemathesis is blocked, follow the fallback in §11.



## P5 — CI v1

Attach: rule, `TESTING_ARCHITECTURE.md` §9 and §9.2 (the corrected `ci.yml` skeleton; nothing else).

> Create `.github/workflows/ci.yml` with jobs: `lint`, `security` (ruff S, pip-audit, gitleaks), `unit`, `component-contract` (matrix over services, `services:` postgres + redis + redpanda (with `command`, architecture §9), `TEST_KAFKA_BOOTSTRAP`, `TEST_PG_URL`, `TEST_REDIS_URL`, `SCHEMA_EXAMPLES=40`, `--cov` + artifact), `ci-gate` (idiom from §9.2: `if: always()` + `toJSON(needs)` checked with `jq`, `success` or `skipped`). `concurrency` cancel, `astral-sh/setup-uv` cache, JUnit upload + job summary. Trigger: pull_request, push main (no merge queue on personal repos), schedule for nightly. Pin third-party actions by SHA (`pinact`/Dependabot, never invent SHAs), `permissions: contents: read`, `timeout-minutes` per job, `uv sync --locked`, no `merge_group`, no GHCR push. Postgres service container with the test tuning (§6.2, ADR-18).
> DoD: push a branch, PR is green; break a test on purpose → gate is red; revert.

---



## P6 — Integration stack + tests

Attach: rule, SUT_MAP, `TESTING_ARCHITECTURE.md` §6.7, §7 (integration).

- **P6.1 (strong model):** `infra/docker-compose.test.yml` (gateway published on :8001, WireMock, `WEBHOOK_URL` of dispatcher AND scheduler → WireMock, timing knobs, `postgres` with ADR-18 `command` + tmpfs; **nginx is not relaxed**), explicit service list, `/health` polling, `src/saas_testkit/infra/compose.py` (`BASE_URL` env-or-up, `KEEP_STACK`), seed + login once per run (FileLock, token file with expiry check), adapters: Kafka reader, MailHog, WireMock, real-network `HttpTaskApi`/`HttpAuthApi`, `tests/integration/conftest.py`.
DoD: `make stack-up` healthy; one test (`login → create task → task readable`) green with `-n 3`.
- **P6.2** `integration/services`: health via gateway, auth→gateway→task JWT flow, nginx dedicated (serial), `/metrics` series.
- **P6.3** `integration/scenarios`: S1, S3, S4 first (fast); S2 and S5 marked `slow`/`chaos`.
DoD: `make t-int` green ×2, no test uses `sleep`, all data unique, works with `KEEP_STACK=1`.



## P7 — Playwright UI

Attach: rule, SUT_MAP, `frontend/src` (pages + components only), `TESTING_ARCHITECTURE.md` §7 (e2e_ui).

1. prod Frontend code (if needed for Playwright POM/POC): accessible names / `data-testid` on login form, board columns, task cards.

> Pages: `LoginPage`, `BoardPage`; components: `KanbanColumn`, `TaskCard` (locators in `__init__`, prefer roles/labels; if the frontend has no accessible names/test ids, list the missing ones in `KNOWN_ISSUES.md` and use the most stable CSS). `tests/e2e_ui/conftest.py`: `browser_context_args` (`service_workers=block`, `storage_state` from the per-run token file), API data fixtures, flows in business language. Drag-and-drop (dnd-kit) goes through one helper using `mouse.move(..., steps=N)`, not `drag_to`. Tests per catalogue; `@pytest.mark.critical` on login+create+move.
> DoD: `make t-ui` green headless; failure produces trace + screenshot; `-n 2` stable ×3.



## P8 — Smoke + synthetic

- **P8.1 smoke:** `tests/smoke/` per catalogue (health of all services via gateway, login both roles, create+read, metrics, frontend 200). Reads `SMOKE_BASE_URL`. `make t-smoke`. `.github/workflows/smoke.yml` (`workflow_call` + `workflow_dispatch`; reused by CI after the stack is up).
DoD: `SMOKE_BASE_URL=http://localhost make t-smoke` green; wrong URL → fails fast with a clear message.
- **P8.2 synthetic:** `tests/synthetic/api/test_critical_path.py` (and optional `browser/`) per catalogue: dedicated synthetic user from env, `X-Synthetic: true`, per-step latency budgets (soft warn / hard fail), step timings in JUnit/job summary. `make t-synthetic`. `.github/workflows/synthetic.yml` with `cron */5` (API) / `*/30` (browser) and issue after 3 consecutive failures, but **commented-out schedule,** `workflow_dispatch` **only** (lab is local; enable cron when a reachable URL exists). Add `make synthetic-local` (shell loop, every 5 min, `SYNTHETIC_BASE_URL=http://localhost`).
DoD: `make synthetic-local` runs two cycles green; a deliberately slow step trips the budget; workflow lints (`actionlint`).
- **P8.3 Grafana Synthetic Monitoring (optional stretch, recommended continuous monitor for the local lab; first to cut):** sign up for Grafana Cloud Free; write `testing/synthetic/k6/critical_path.js` (login → create → read; reuse `load-tests/lib/helpers.js`); run a private probe (outbound-only, no tunnel/ngrok needed) via `testing/synthetic/compose.probe.yml` (follow current Grafana docs for the agent image/flags); create the check, an alert, and a dashboard. Do not commit tokens.
DoD: check shows green in Grafana Cloud with the lab running; stopping task-service turns it red and fires the alert.



## P9 — CI v2

> Extend `ci.yml`: `integration` (builds the needed images inside the job with buildx + gha cache, compose up of an explicit service list, `/health` polling, `BASE_URL`, `-n 3`, logs artifact on failure), `smoke` (reuse `smoke.yml` after the stack is up; blocks), `ui-e2e` (Playwright per architecture §9.3: browser cache keyed by Playwright version + `install-deps`, `-n 2`, `-m critical` on PR, full on push to main, traces artifact), `ci-gate` needs all (append every new job to its `needs`). Add a `shard` matrix to `integration` and `ui-e2e` (`shard: [1]` by default, `pytest-split --splits ${{ strategy.job-total }} --group ${{ matrix.shard }}`, `.test_durations` cached) so scale-out is a one-line change (see architecture §12). Add `nightly.yml`: Schemathesis 500 examples, `slow` + `chaos`, firefox/webkit matrix, `--count 5` flaky pass, `.test_durations` refresh. Add `coverage` job combining service coverage.
> DoD: a PR runs the full DAG green; `needs` prevents e2e when lint fails; artifacts downloadable.



## P10 — Polish (first thing cut)

- `testing/README.md`: purpose, layer diagram, how to run each layer, ADR summary, CI badge, findings summary (from `KNOWN_ISSUES.md`), screenshot of a trace/report.
- `reporting.py` failure links (Jaeger/Kibana by correlation id), API-coverage meta-test if time.
- Final run: `make t-lint && make t-unit && make t-component-all && make t-contract && make t-int && make t-ui`.

---



## E. Optional improvement (after P10, before refactor)

1. **Affected-only CI**: `dorny/paths-filter` per service/shared/frontend/infra; `ci-gate` still requires the full set on `main`; shared/`saas_shared`/`infra` changes trigger everything.



## F. After testing (a separate prod-code refactoring + unit tests work)

**R0 (do not forget): migrate** `requirements.txt` **→** `uv` **+** `pyproject.toml` **for every service and** `saas_shared` (uv workspace or path dependencies, lockfile, Dockerfiles use `uv sync --frozen`). Payoff for tests: services install as packages (no `sys.path` hacks in `conftest.py`), each service can run in its own environment (`uv run --package <svc> pytest`), `saas_testkit` becomes a normal dependency. Re-run all suites after R0; it is a pure packaging change.  

**Order of the refactoring phase (workers and scheduler first, under the integration safety net):**

1. Write the integration scenarios S1–S4 plus scheduler scenarios (cleanup, DLQ replay with shortened knobs) and make them green on the current code.
2. Unify scheduler-worker on async SQLAlchemy + aiokafka: Celery tasks stay thin synchronous wrappers around `asyncio.run(...)` of async service functions (create the engine inside each run); drop `psycopg2` and `kafka-python`. Re-run the integration scenarios.
3. Restructure the remaining services; then write worker/scheduler component and unit tests (P3.5–P3.6) once, against the final structure.
4. Replace cp-kafka + ZooKeeper with KRaft in the lab compose. Remove the zookeeper service entirely. Make sure to preserve existing network settings, and ensure that other services like kafka-exporter and python services can still connect to Kafka on the correct internal ports.

Refactor service by service with the suite as safety net: for each service, run its component + contract + integration subset before/after; write its unit tests in `services/<svc>/tests/unit` using `saas_testkit.factories` (path dependency: `uv add --dev ../../testing`). Add two rules then: `refactor.mdc` (manual `@`: characterization tests first, one service per branch, no behaviour change, layers `api / application / domain / infrastructure`, run the service's component + contract suites before and after) and `unit-tests.mdc` (globs `services/**/tests/unit/**`: pure-function tests, pytest-mock `autospec=True`, no DB/Kafka/Redis/HTTP, `.build()` factories only). `python-style.mdc` already covers prod code. Remove Datadog in one dedicated commit (compose overlay, `ddtrace-run`, env, docs) and re-run everything.