# Review: Cursor doc pack vs. source docs, and 2026 / Python 3.14 best-practice check

Date: 2026-10-04. Reviewer role: Principal SDET.
Scope: `testing/docs/cursor/**`, `.cursor/rules/*.mdc`, `.cursorignore` checked against
`testing/docs/TESTING_ARCHITECTURE.md` and `testing/docs/IMPLEMENTATION_PLAN.md`, then against the
actual repository (compose, nginx, Dockerfiles, requirements) and against current package versions on PyPI,
and the agent workflow itself (rules attachment, prompt template, DoD loop, context budget).

## 1. Verdict

- **Split is lossless.** Every section of `TESTING_ARCHITECTURE.md` (§1–§13, incl. all 18 ADRs, both YAML
skeletons, all catalogue lines, all 8 risk rows, all 10 anti-patterns) and every block of
`IMPLEMENTATION_PLAN.md` (A–F, P0–P10, every DoD) is present in exactly one pack file. The pack adds a few
things the originals lack (explicit time-boxes, the §6.4 DI fallback sentence, `make contracts-update`
in principle 3, Redpanda in `compose.deps.yml`), and all of them are consistent with the originals.
- **Rules are consistent with the docs**, with one real conflict: `python-style.mdc` prescribes 3.14-only
syntax for `**/*.py`, but every service Dockerfile is `python:3.11-slim` (see 6.5).
- **The main problems are not in the split; they are facts the original docs got wrong about the repo**
(service paths, nginx rate-limit semantics, Postgres major, worker readiness, Testcontainers extras).
They should be fixed in both the originals and the pack before P0.2/P1 (list in §9).
- **Design quality:** the architecture is at or above 2026 Senior-SDET expectations (uv + src-layout,
controller-owned Testcontainers + template DB per xdist worker, real Redpanda, exact contract snapshots,
never-silence-500, sync Playwright with storage_state, SHA-pinned CI with a correct `ci-gate`). Gaps are
listed in §8 and are mostly additive.
- **Workflow is sound.** Rules = invariants, docs attached per phase, `SUT_MAP.md` as the compressed fact
sheet, one task per chat with a runnable DoD and a `git restore` reset path, golden example then
replicate, mutation spot-check. Nine practical hazards are listed in §10; none needs a redesign.



## 2. Architecture split: section-by-section map


| `TESTING_ARCHITECTURE.md`                          | Pack file                           | Result                                                                                                                          |
| -------------------------------------------------- | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| header, §1 goals, §1.1 terms, §2 ADR 1–18          | `design/arch-adr.md`                | complete; ADR-12 gains "15 min", ADR-14 gains ">30 min" (both match the plan)                                                   |
| §3 SUT cheat sheet, §4 pyramid + matrix, §5 layout | `design/arch-layers-layout.md`      | complete; `compose.deps.yml` comment corrected to include Redpanda (original was internally inconsistent with ADR-2/5 and P0.2) |
| §6.1, §6.2, §6.4, §6.6                             | `design/arch-core-infra.md`         | code identical; §6.4 gains the "no DI seam" fallback sentence                                                                   |
| §6.3, §6.5                                         | `design/arch-adapters-factories.md` | code identical; note (2) of §6.5 moved to `testing-core.mdc` with a pointer; note (3) loses only "in the root conftest"         |
| §6.7 + §7 integration lines                        | `design/arch-integration.md`        | complete (7 bullets, services line, S1–S5)                                                                                      |
| §7 component lines                                 | `design/cat-component.md`           | all 8 services, text identical                                                                                                  |
| §7 contract lines + §7.1                           | `design/cat-contract.md`            | complete                                                                                                                        |
| §7 e2e_ui line                                     | `design/cat-ui.md`                  | complete                                                                                                                        |
| §7 smoke + synthetic lines, §9.1 Grafana           | `design/cat-smoke-synthetic.md`     | complete, incl. all synthetic requirements and the 100k/8.6k numbers                                                            |
| §8, §10, §11, §13                                  | `design/arch-quality.md`            | complete; §11 gains time-boxes                                                                                                  |
| §9, §9.2, §9.3, §12                                | `design/arch-ci.md`                 | YAML identical; DAG picture converted to prose (ok)                                                                             |


Cross-references inside the pack (`arch-core-infra.md §6.2`, `arch-ci.md §9.2`, `arch-quality.md §11`,
`cat-smoke-synthetic.md`, `testing-core.mdc "Data and isolation"`, `p10 section F`) all resolve.

## 3. Plan split: section-by-section map

- A, B, D → `plan/00-workflow.md`: all 16 bullets of B are present (duplicates "pattern once / golden
example" and "plan first" were merged, nothing dropped); cut-line order identical.
- C → `plan/01-prompt-template.md`: verbatim.
- P0, P0.1, P0.2 → `plan/p0-recon-prep-bootstrap.md`: verbatim (dependency list, `testing.mk` targets,
dependency-group paragraph, minimal CI, DoDs, `[DONE]` marker).
- P1…P9 → `plan/p1…p9`: verbatim bodies and DoDs; "Attach" lines translated from § numbers to pack
files correctly (P1 = adr + core-infra + adapters-factories; P4 = cat-contract + quality §11 row).
- P10, E, F → `plan/p10-polish-after.md`: verbatim incl. R0, refactor order 1–4, the two future rules.



## 4. Rules vs. docs

- `testing-core.mdc`: consistent with ADR 1–11, §6, §10, §13. Two nits: (a) markers `db`, `redis`,
`kafka` are declared but never defined anywhere in the architecture (give them a purpose, e.g. input to
`needs_infra` / local `-m "not kafka"`, or drop them); (b) "Design docs live in testing/docs/cursor/"
— they live in `testing/docs/cursor/design/`.
- `playwright.mdc`: consistent with ADR-8, cat-ui, P7 (dnd helper, storage_state, `critical`).
- `testing-modify-prod.mdc`: consistent with ADR-14 and P0.1.
- `python-style.mdc`: consistent with the testing code. **Conflict with prod runtime**: the rule applies
to `**/*.py`, forbids `from __future__ import annotations` and asks for PEP 695 generics, `type` aliases,
`@override` — all 3.12–3.14 features — while services and workers run on `python:3.11-slim` and
`shared/pyproject.toml` says `requires-python >= 3.11`. Following the rule on a `testability:` seam
would break a service image. Fix: scope the rule to `testing/**/*.py` until R0 bumps the images, or add
one line "prod code stays 3.11-compatible until R0".



## 5. INDEX.md and .cursorignore

- `INDEX.md` line 2 says `docs/*.md -> testing/docs/cursor/`; the folder is `design/`. Everything else in
the task→files map matches the phase files.
- `.cursorignore` differs from the list in 00-workflow.md / plan §B:
  - ignores the whole `frontend/` (plan: only `node_modules`, "unignore `frontend/src` for P7").
  P0.1 item 5 (`vite build` + `preview` target) and P7 both need frontend files: un-ignore
  `frontend/src`, `frontend/vite.config.*`, `frontend/Dockerfile`, `frontend/package.json` when those
  tasks start.
  - ignores `load-tests/lib` while P8.3 says "reuse `load-tests/lib/helpers.js`".
  - adds `docs/cheat-sheets`, `docs/on-call`, `docs/system-architechture/testing-architecture` (fine).
  - `infra/**/grafana` is missing but covered by `observability/` (Grafana provisioning lives there).
  - The ignore is enforced for agents (reads of ignored paths fail with "permission denied"), so the
  P0 recon prompt's "Attach: lab README, ARCHITECTURE, FILE_STRUCTURE" works, but `SERVICE_MAP.md`
  (exists, not mentioned) is a useful extra input for P0.



## 6. Docs vs. the real repository (fact check)

These apply to the originals and the pack alike.

### 6.1 Service paths

Docs use `services/<svc>` everywhere (`--cov=../services/${{ matrix.service }}`, `services/*/tests/unit`,
`uv add --dev ../../testing`). Actual layout: `services/core/{api-gateway,auth-service,task-service, webhook-dispatcher,webhook-receiver}`, `services/external/external-service-simulator`,
`workers/{notification-worker,scheduler-worker}`, `migrations/`, `shared/`. `config/services.py`
(name → path) absorbs this for pytest, but the ci.yml `--cov` path and the F-section relative path
(`../../../testing` from `services/core/<svc>`) must be corrected.

### 6.2 nginx rate limiting (ARCHITECTURE.md and the cheat sheet are stale)

`infra/nginx/nginx.conf`:

- both zones are keyed by `$http_authorization`, not by IP: `zone=api rate=20r/s`, `zone=auth rate=5r/m`;
- `location /` → `limit_req zone=api burst=100` (delayed, not `nodelay`); `/webhooks/` burst 20 nodelay;
- only `/auth/token` uses the auth zone; `/auth/` (incl. `/auth/me`) is unlimited.
Consequences:
- A login request carries no `Authorization` header → empty key → nginx does not account it
(documented nginx behaviour). The brute-force limit is effectively inactive. The planned integration
test "nginx 429 on auth burst" will most likely not see a 429: that is a legitimate **BUG-1 candidate
for** `KNOWN_ISSUES.md`, not a test problem.
- The API limit is per bearer token. "Login once per run, shared token file" therefore routes all UI and
nginx-edge traffic into one 20 r/s bucket (burst 100). The design conclusion still holds (functional
tests → gateway `:8001`; UI via nginx with `-n 2`), but the rationale "per IP" in §3/§11/
`testing-core.mdc` is wrong and should be rewritten as "per token".
- P0 recon must derive SUT_MAP from code, not from ARCHITECTURE.md (the plan already says so; the
cheat sheet should carry a "provisional until SUT_MAP" note).



### 6.3 Postgres major

Lab compose runs `postgres:15`; the CI skeleton uses `postgres:17-alpine`. Test against the same major as
the lab (or upgrade the lab in R0 and change both). `compose.deps.yml`, Testcontainers image and the CI
service must share one pinned tag; keep the §6.2 tmpfs path note.

### 6.4 Readiness of workers

Only 10 compose services have healthchecks (postgres, redis, zookeeper, kafka, api-gateway, nginx, auth,
task, simulator, receiver). Workers, migrations, mailhog, toxiproxy, frontend have none, which confirms
P0.1 item 5. But "poll `/health` of every service" cannot work for webhook-dispatcher, notification-worker
and scheduler-worker (no HTTP app; metrics on `:9100`). Define readiness per kind: FastAPI → `/health`;
workers → `GET :9100/metrics` or consumer group joined (Kafka admin API); migrations → container exit 0.

### 6.5 Interpreter and dependency drift between tests and prod

Component/contract tests import service code in-process under Python 3.14 with uv-locked versions; the
shipped containers run 3.11 with **unpinned** `requirements.txt` (resolved at image build). Tested ≠
shipped for interpreter and library versions. Acceptable for the lab if stated in README and ADR-12, and
R0 should bump the Dockerfiles to 3.14 so the gap closes. Related: SQLAlchemy 2.1.x is current on PyPI
(requires ≥3.11); unpinned services will pick it up on the next image build — check `saas_shared.models`
against 2.1 in P0 and pin `sqlalchemy>=2.0,<2.2` in the kit.

### 6.6 Datadog is scheduled twice

P0.1 item 1 removes Datadog before the kit; section F ends with "Remove Datadog in one dedicated commit".
Pick P0.1 (it blocks in-process imports), delete the sentence in F, and exclude `ddtrace` from the
per-service uv dependency groups (it is in every `requirements.txt`).

### 6.7 User-rule paths

The workspace user rule says "follow `docs/ARCHITECTURE.md`" and "read `docs/PROJECT_SPEC.md`".
The first lives at `docs/system-architechture/ARCHITECTURE.md`; the second does not exist. Every chat
starts by failing that rule; fix the paths or add the file.

## 7. Ecosystem check (PyPI, 2026-10-04)

- cp314 wheels exist for every compiled dependency named in ADR-12: asyncpg 0.31, aiokafka 0.14,
greenlet 3.5, psycopg-binary 3.3, SQLAlchemy 2.1. ADR-12's "drop to 3.13" fallback is now unlikely to
trigger (keep it; free-threaded `cp314t` wheels were not checked — stay on the GIL build).
- pytest 9.1, pytest-asyncio 1.4 (`asyncio_default_fixture_loop_scope` / `asyncio_default_test_loop_scope`
are the correct option names; the `event_loop` fixture is gone, so the session-loop design is right),
pytest-xdist 3.8, pytest-randomly 5.0, pytest-split 0.11, pytest-rerunfailures 16.x.
- Polyfactory 3.3: `__async_session__`, `__set_relationships__`, commit-by-default persistence confirmed.
- Schemathesis 4.29: entry points are `schemathesis.openapi.from_asgi(path, app)` / `from_url`; stateful
via `schema.as_state_machine()`. The docs' wording is compatible.
- **Testcontainers 4.15: there is no** `redpanda` **extra.** Extras are `postgres`, `redis`, `kafka`;
Redpanda is `from testcontainers.community.kafka import RedpandaContainer`. The legacy
`testcontainers.postgres` / `.redis` / `.kafka` modules are deprecation shims → use
`testcontainers.community.*`. `DockerContainer.with_tmpfs_mount(path, size=None)` exists — prefer it to
`with_kwargs(tmpfs=...)`. P0.2's `testcontainers[postgres,redis,redpanda]` must become
`testcontainers[postgres,redis,kafka]`.
- GitHub Actions: `jobs.<id>.services.<id>.command` and `.entrypoint` are documented keys (verified in
the current workflow-syntax reference), so the Redpanda/Postgres service-container approach in §9.2
is valid.
- httpx 0.28 (`ASGITransport` does not run lifespan — docs correct), respx 0.23, Playwright 1.63 with
pytest-playwright 0.9 (sync) and pytest-playwright-asyncio 0.9 (ADR-8 reasoning still accurate),
redis-py 8.1, pydantic 2.13, uv 0.12, ruff 0.16, pyright 1.1.414.



## 8. Best-practice assessment (2026, Python 3.14)



### What is already at the expected level

- Packaging: uv, one `pyproject.toml`, src-layout + hatchling, PEP 735 dependency groups per service,
`uv sync --locked` in CI.
- Isolation model: controller-owned infra, `pytest_configure_node` hand-off, template DB per xdist worker
with real commits, trigger-based touched-table truncate on demand, Redis DB index per worker, unique
data everywhere, fresh Kafka consumer group per test. This is the strongest part of the design.
- Real dependencies over fakes (Redpanda, PG, Redis), with `respx` and `mocker.patch(autospec=True)`
only for failure injection; explicit respx-vs-WireMock boundary.
- Contract layer: exact snapshots with reviewed updates, consumer-side tolerant models, never-silence-500,
Schemathesis light on PR / deep nightly.
- UI: sync Playwright, browser per worker, context per test, storage_state from one API login,
role/label locators, web-first assertions, trace/screenshot on failure, dnd via mouse steps.
- CI: SHA-pinned actions, minimal permissions, per-job timeouts, `ci-gate` with `if: always()` +
`toJSON(needs)`, concurrency cancel, service containers with tuning, sharding pre-wired, dormant
synthetic workflow with a documented reason.
- Quality policy: strict markers, randomised order, strict xfail tied to KNOWN_ISSUES, reruns only where
justified and always reported, mutation spot-check.



### Gaps and upgrades, by priority

1. **Fix the fact errors in §6 of this review first** (paths, nginx, PG major, worker readiness,
  Testcontainers extra, Datadog duplication, python-style scope). They would cost time in P0.2–P1 and P5.
2. **One seed to reproduce a run.** pytest-randomly reseeds `random`/Faker per test, but Polyfactory uses
  its own `Random` instance. Set `Factory.seed_random(config.getoption("randomly_seed"))` so the number
   printed by pytest-randomly reproduces both test order and factory data; drop the separate `run_seed`.
3. **Serial tests via xdist, not a custom marker.** Map `serial` to `@pytest.mark.xdist_group("serial")`
  and run integration with `--dist loadgroup`; it is native, and the nginx edge tests stay serialised
   under `-n 3` without extra plumbing.
4. **Coverage under xdist + async SQLAlchemy.** Add `[tool.coverage.run] parallel = true`,
  `concurrency = ["thread", "greenlet"]`, `sigterm = true`; SQLAlchemy's async layer runs ORM internals in
   greenlets and code executed there (ORM event hooks, sync callbacks) is otherwise unmeasured.
5. **Property-based state-machine test** for the task lifecycle with Hypothesis `RuleBasedStateMachine`
  at component level (Hypothesis is already a transitive dependency via Schemathesis). Cheap, and it
   complements the parametrised 409 matrix with generated transition sequences.
6. **Event contracts as AsyncAPI.** Keep the JSON-schema snapshots, but reference them from a committed
  `contracts/asyncapi.yaml` (AsyncAPI 3). Same exactness, standard format; one line in ADR-17 on why not
   Pact (single repo, no independent deploys, consumer/provider in one PR) pre-empts a standard interview
   question.
7. **Test-run tracing.** The kit already sends `traceparent` and prints Jaeger links; exporting the pytest
  run itself as a trace (`pytest-opentelemetry` or a 20-line plugin on the OTEL SDK) into the lab's
   Jaeger gives one trace from test → nginx/gateway → service → Kafka → worker. In an observability lab
   this is the most visible portfolio feature for the cost.
8. **KRaft earlier than F.4.** Moving cp-kafka 7.5 + ZooKeeper to KRaft is infra-only (no prod code),
  removes a container and shortens integration-stack boot; doing it before P6 pays back during P6–P9.
9. **Pin service requirements before P3** (packaging-only, behaviour-neutral) so component tests and
  images resolve the same versions; R0 then only changes the tool, not the versions.
10. **Readiness semantics in** `compose.py`: per-kind readiness (see 6.4) plus a hard timeout and a
  `docker compose logs --tail` dump on failure, locally and in CI.
11. Smaller items: `step-security/harden-runner` in CI; `axe-core` accessibility check in one UI test;
  `python -m asyncio ps/pstree` (new in 3.14) as the documented way to debug hung async tests; a
    `make stack-reset` for `KEEP_STACK=1` local runs; mention `load-tests/` (k6) as the performance layer
    in the pyramid picture even though it is out of scope; name 3.14 `concurrent.interpreters` in ADR-1
    as a considered-and-rejected alternative to one-process-per-service.



## 9. Recommended edits (items 1–13: originals and pack; 14–21: rules, template, workflow files)

1. `arch-layers-layout.md` §3 cheat sheet + `TESTING_ARCHITECTURE.md` §3: nginx row → "zones keyed by
  `Authorization` header: API 20 r/s burst 100 (delayed) on `/`, burst 20 nodelay on `/webhooks/`;
   `/auth/token` 5 r/m burst 3 but login has no `Authorization` → not limited (BUG candidate)". Mark the
   whole table "provisional until SUT_MAP".
2. `arch-quality.md` §11 last row, `testing-core.mdc` "Data and isolation": replace "per IP" reasoning
  with "per token".
3. `arch-ci.md` §9.2 and `TESTING_ARCHITECTURE.md` §9.2: `postgres:15` (match the lab) or decide to
  upgrade both; `--cov` path from `config/services.py`, not `../services/<svc>`.
4. `p0-recon-prep-bootstrap.md` P0.2 and plan P0.2: `testcontainers[postgres,redis,kafka]`; exclude
  `ddtrace` from dependency groups.
5. `arch-core-infra.md` §6.2 / `TESTING_ARCHITECTURE.md` §6.2: `with_tmpfs_mount(...)`; imports from
  `testcontainers.community.*`.
6. `arch-integration.md` §6.7 and P6.1: readiness per service kind (workers via `:9100/metrics`).
7. `p10-polish-after.md` F and plan F: drop the duplicate Datadog sentence; fix `uv add --dev` relative
  path (`../../../testing` from `services/core/<svc>`, `../../testing` from `workers/<svc>`).
8. `python-style.mdc`: `globs: testing/**/*.py` until R0, or add the 3.11-compat line for prod code.
9. `testing-core.mdc`: define or remove `db`/`redis`/`kafka` markers; fix the design-docs path.
10. `INDEX.md`: `docs/*.md` → `design/*.md`.
11. `.cursorignore`: replace `frontend` with `frontend/node_modules` + `frontend/dist` (or keep it and
  un-ignore `frontend/src`, `vite.config.*`, `Dockerfile`, `package.json` at P0.1/P7); un-ignore
    `load-tests/lib` for P8.3.
12. User rule: point to `docs/system-architechture/ARCHITECTURE.md`; create or drop `PROJECT_SPEC.md`.
13. `arch-adr.md`: ADR-12 note that cp314 wheels are available (fallback kept); ADR-17 add the Pact
  sentence; ADR-1 add the `concurrent.interpreters` non-choice.

Items 14–21 implement the agent-workflow findings of §10:

1. `INDEX.md`: declare the pack canonical; add a one-line regeneration note for the monoliths (`cat` of
  the pack files in INDEX order) or mark `TESTING_ARCHITECTURE.md` / `IMPLEMENTATION_PLAN.md` as
    "derived, do not edit by hand" (§10.1).
2. `testing-core.mdc`: remove SUT numbers (the nginx line becomes "rate limits: see SUT_MAP"); add the
  blocked-read line "If a file you need is unreadable or not in SUT_MAP, stop and report; never infer
    routes, fields or selectors"; set `alwaysApply: true` unless item 16 is chosen (§10.2–§10.4).
3. `plan/01-prompt-template.md`: add `@testing-core.mdc` to the template; split the DoD into an inner
  loop (`pytest <file> -x -q --lf -n 0`) and a final `make t-gate` (§10.3, §10.7).
4. New `testing/docs/cursor/KIT_MAP.md` (30–50 lines: public fixtures, flows, factories, markers, make
  targets); add "update KIT_MAP" to the DoD of `p1`, `p2`, `p6` (P6.1) and `p7`; add KIT_MAP to the
    INDEX attach map for P3–P9 (§10.5).
5. `KNOWN_ISSUES.md` (or `INDEX.md`): a "Decisions since the plan" section, one line per deviation
  (§10.6).
6. `testing.mk` (via the P0.2 prompt in `p0-recon-prep-bootstrap.md`): add a `t-gate` target = 3 runs,
  random order, `-n auto`, for the layer or service given (§10.7).
7. `arch-core-infra.md`, `arch-adapters-factories.md`, `arch-ci.md` (and monolith §6, §9.2): mark every
  placeholder in the skeletons with `# PLACEHOLDER: from SUT_MAP` or `# PLACEHOLDER: resolve` (§10.8).
8. `plan/p*.md`: rewrite telegraphic lines ("same note", "see p10") as full sentences and separate
  "must" from "may" (§10.9).



## 10. Working with LLM agents: what will hurt, and the fix



### Keep as is

- Rules carry invariants and are small; docs carry rationale and skeletons and are attached per phase.
The `Attach:` line of each phase file is an explicit context budget.
- `SUT_MAP.md` is the single most valuable token-economy device: a compressed fact sheet instead of the
whole repository.
- One task = one chat, commit per green task, time-boxes, "stop after 3 failed fixes", a ≤10-line report.
These are the right guardrails for autonomous loops and keep a bad chat reversible with `git restore`.
- Golden example then "replicate for auth-service" exploits what models do best.
- Strong model in Plan/Ask for P1, P2, P6 design; cheaper model in Agent mode for mechanical P3, P4, P7.



### Hazards and fixes



#### 10.1 Two sources of truth

Finding: the monoliths (`TESTING_ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md`) and the pack already
diverged: the `compose.deps.yml` Redpanda fix exists only in the pack.
Why it hurts agents: a chat that attaches the monolith gets a different fact than a chat that attaches
the pack, and nobody notices until a test is built on the stale one.
Fix: declare the pack canonical and regenerate the monolith (a `cat` of the pack files in INDEX order is
enough), or stop maintaining the monolith. Never edit both by hand.

#### 10.2 SUT facts inside an always-on rule

Finding: `testing-core.mdc` states "Nginx /auth/ allows 5 req/min", a stale fact (see §6.2) baked into an
invariant file.
Why it hurts agents: agents treat rules as ground truth and do not re-verify them against the code.
Fix: rules contain only policy; every SUT number belongs in `SUT_MAP.md`, and the rule says "see SUT_MAP".

#### 10.3 Glob-attached rules are not attached at chat start

Finding: with `alwaysApply: false`, `testing-core.mdc` attaches only once a `testing/**` file is in
context.
Why it hurts agents: the first steps of a fresh chat (creating new files from a pasted prompt) can run
without the rule that defines layers, markers and isolation.
Fix: `alwaysApply: true` for `testing-core` (it is ~1.2k tokens), or put `@testing-core.mdc` into the
prompt template.

#### 10.4 Blocked reads turn into invented facts

Finding: `.cursorignore` is enforced; reads of ignored paths fail with "permission denied".
Why it hurts agents: when an agent cannot read `frontend/src` or `load-tests/lib` it tends to guess
routes, selectors or helper names rather than stop.
Fix: add one line to `testing-core`: "If a file you need is unreadable or not in SUT_MAP, stop and report;
never infer routes, fields, or selectors." Un-ignore what P0.1, P7 and P8.3 need before those phases
(see §5).

#### 10.5 Nothing describes the testkit after P2

Finding: `SUT_MAP.md` covers the system under test; nothing covers `saas_testkit` once it exists.
Why it hurts agents: from P3 on, an agent that does not know the kit's fixtures, flows, factories and
markers re-creates helpers, producing duplicates and inconsistent patterns.
Fix: add a 30–50-line `testing/docs/cursor/KIT_MAP.md` (public fixtures, flows, factories, markers, make
targets) and make "update KIT_MAP" part of the DoD for P1, P2, P6.1 and P7. Keep
`saas_testkit/**/__init__.py` exports clean so the agent can also read them directly.

#### 10.6 No place to record deviations from the plan

Finding: when P1 picks `postgres:15` or `-n 2` becomes `-n 1`, later chats have no way to know.
Why it hurts agents: settled questions get re-litigated, or a later chat "fixes" a deliberate deviation
back to the plan.
Fix: a short "Decisions since the plan" section in `KNOWN_ISSUES.md` or `INDEX.md`, one line per
deviation.

#### 10.7 The DoD is too heavy for the inner loop

Finding: "3× random order, `-n auto`, Docker" is the DoD per fix attempt.
Why it hurts agents: every retry in a fix loop pays the full gate, making loops slow and expensive and
pushing the agent toward its 3-fix limit on timing alone.
Fix: split it. Inner loop = `pytest <file> -x -q --lf -n 0`; final gate = `make t-gate` (3×, random
order, `-n auto`) run once at the end, by you or as the last step. The plan hints at this; make it
explicit in the template.

#### 10.8 Skeletons get copied literally

Finding: despite "adapt, do not copy blindly", the skeletons contain placeholders (`...`, `<SHA>`,
`"invalid_transition"`, `../services/<svc>`) that look like real values.
Why it hurts agents: a placeholder that is syntactically valid is indistinguishable from a real name and
gets pasted as is.
Fix: mark them visibly (`# PLACEHOLDER: from SUT_MAP`, `# PLACEHOLDER: resolve`) so an agent cannot
mistake them for real names.

#### 10.9 Over-compression in the phase files

Finding: the phase files use a telegraphic style ("same note", "see p10").
Why it hurts agents: the saved tokens do not matter at ~2k tokens per doc, while the lost precision
produces ambiguity about what is mandatory and what is optional.
Fix: keep rules terse; let phase files use full sentences and separate "must" from "may".

## Appendix: evidence

- Repo: `infra/docker-compose.yml` (images, 10 healthchecks, profiles), `infra/nginx/nginx.conf`
lines 42–113, `services/**/Dockerfile` + `workers/**/Dockerfile` (`python:3.11-slim`),
`*/requirements.txt` (unpinned, `ddtrace` everywhere), `shared/pyproject.toml`
(`requires-python >= 3.11`), `scripts/seed_dev.py` (exists), `docs/` (no `PROJECT_SPEC.md`).
- PyPI JSON API queried for 27 packages; testcontainers 4.15.0 sdist inspected
(`src/testcontainers/community/kafka/_redpanda.py`, `core/container.py::with_tmpfs_mount`,
deprecation shims in `src/testcontainers/{postgres,redis,kafka}.py`).
- GitHub workflow-syntax reference: `jobs.<job_id>.services.<service_id>.{command,entrypoint}` present.
- Agent workflow: all four rules have `alwaysApply: false`; `testing-core` and `playwright` attach by
glob only when a matching file is in context (§10.3). `.cursorignore` is enforced for agent reads:
during this review, `ls`/`find` on `frontend/`, `load-tests/lib`, `chaos/`, `observability/` and
`docs/system-architechture/testing-architecture` returned "permission denied" (§10.4).

