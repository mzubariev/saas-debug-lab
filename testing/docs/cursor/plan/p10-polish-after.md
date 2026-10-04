# P10 polish (first thing cut), E optional, F after testing

## P10 - Polish
- testing/README.md: purpose, layer diagram, how to run each layer, ADR summary, CI badge, findings summary (from KNOWN_ISSUES.md), screenshot of a trace/report.
- reporting.py failure links (Jaeger/Kibana by correlation id), API-coverage meta-test if time.
- Final run: `make t-lint && make t-unit && make t-component-all && make t-contract && make t-int && make t-ui`.

## E - Optional improvement (after P10, before refactor)
1. Affected-only CI: dorny/paths-filter per service/shared/frontend/infra; ci-gate still requires the full set on main; shared/saas_shared/infra changes trigger everything.

## F - After testing (a separate prod-code refactoring + unit tests work)
R0 (do not forget): migrate requirements.txt -> uv + pyproject.toml for every service and saas_shared (uv workspace or path dependencies, lockfile, Dockerfiles use `uv sync --frozen`). Payoff: services install as packages (no sys.path hacks in conftest.py), each service runs in its own environment (`uv run --package <svc> pytest`), saas_testkit becomes a normal dependency. Re-run all suites after R0; pure packaging change.

Order of the refactoring phase (workers and scheduler first, under the integration safety net):
1. Write integration scenarios S1-S4 plus scheduler scenarios (cleanup, DLQ replay with shortened knobs) and make them green on the current code.
2. Unify scheduler-worker on async SQLAlchemy + aiokafka: Celery tasks stay thin synchronous wrappers around asyncio.run(...) of async service functions (create the engine inside each run); drop psycopg2 and kafka-python. Re-run the integration scenarios.
3. Restructure the remaining services; then write worker/scheduler component and unit tests (P3.5-P3.6) once, against the final structure.
4. Replace cp-kafka + ZooKeeper with KRaft in the lab compose. Remove the zookeeper service entirely. Preserve existing network settings and make sure other services (kafka-exporter, python services) still connect to Kafka on the correct internal ports.

Refactor service by service with the suite as safety net: for each service run its component + contract + integration subset before/after; write its unit tests in services/<svc>/tests/unit using saas_testkit.factories (path dependency: uv add --dev ../../testing). Add two rules then: refactor.mdc (manual @: characterization tests first, one service per branch, no behaviour change, layers api / application / domain / infrastructure, run the service's component + contract suites before and after) and unit-tests.mdc (globs services/**/tests/unit/**: pure-function tests, pytest-mock autospec=True, no DB/Kafka/Redis/HTTP, .build() factories only). python-style.mdc already covers prod code. Remove Datadog in one dedicated commit (compose overlay, ddtrace-run, env, docs) and re-run everything.
