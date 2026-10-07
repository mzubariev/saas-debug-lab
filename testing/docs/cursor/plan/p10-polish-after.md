# P10 polish (cut first if behind), optional improvement E, and the refactoring phase F

## P10: Polish

- Optionally add the failure links in `reporting.py` (Jaeger and Kibana by correlation id) and the API-coverage meta-test.
- Optional, high portfolio value: export the pytest run itself as a trace into the lab's Jaeger (`pytest-opentelemetry`, or a small plugin on the OpenTelemetry SDK; verify the package and versions first, and check that Jaeger accepts OTLP in the lab compose). The run becomes the root span, tests become child spans, and the existing `traceparent` header continues it, so one trace shows test, nginx/gateway, service, Kafka and worker. Do this after P9 and only if time remains.
- Run only the affected parts in CI: use `dorny/paths-filter` per service, shared code, frontend and infra. `ci-gate` still requires the full set on main, and changes to shared code, `saas_shared` or infra trigger everything.
- Run the final check: `make t-lint && make t-unit && make t-component-all && make t-contract && make t-int && make t-ui`.
- Write `testing/README.md`: purpose, layer diagram, how to run each layer, ADR summary, CI badge, a summary of findings from `KNOWN_ISSUES.md`, and a screenshot of a trace or report. State there that the tests run on Python 3.14 with a lockfile while the service images still run Python 3.11 with unpinned requirements (closed in R0).



## A: After testing (a separate production-code refactoring and unit-test effort)

R0 must not be forgotten: migrate `requirements.txt` to `uv` and `pyproject.toml` for every service and for `saas_shared` (a uv workspace or path dependencies, a lockfile, and Dockerfiles that use `uv sync --frozen`). Move the Dockerfiles to Python 3.14 in the same step, so the gap between tested and shipped versions closes, and then lift the 3.11-compatibility restriction in `python-style.mdc`. The payoff for tests is that services install as packages (no `sys.path` hacks in `conftest.py`), each service can run in its own environment (`uv run --package <svc> pytest`), and `saas_testkit` becomes a normal dependency. Re-run all suites after R0; it is a pure packaging change.

Order of the refactoring phase (workers and scheduler first, under the integration safety net):

1. Write the integration scenarios S1 to S4 plus the scheduler scenarios (cleanup, DLQ replay with shortened knobs) and make them green on the current code.
2. Unify scheduler-worker on async SQLAlchemy and aiokafka. The Celery tasks stay thin synchronous wrappers around `asyncio.run(...)` of async service functions (create the engine inside each run). Drop `psycopg2` and `kafka-python`, then re-run the integration scenarios.
3. Restructure the remaining services, then write the worker and scheduler component and unit tests (P3.5 and P3.6) once, against the final structure.
4. Replace cp-kafka plus ZooKeeper with KRaft in the lab compose and remove the zookeeper service entirely. This is normally already done in P6.0; do it here only if P6.0 was skipped. Preserve the existing network settings and make sure the other services (kafka-exporter, the Python services) still connect to Kafka on the correct internal ports.

Refactor service by service with the suite as the safety net: for each service run its component, contract and integration subset before and after, and write its unit tests next to it (`services/core/<svc>/tests/unit`, `services/external/<svc>/tests/unit` or `workers/<svc>/tests/unit`) using `saas_testkit.factories`. The kit is a path dependency: `uv add --dev ../../../testing` from `services/core/<svc>` and `services/external/<svc>`, and `uv add --dev ../../testing` from `workers/<svc>`.

At that point add two rules. `refactor.mdc` is attached manually with `@`: write characterization tests first, work on one service per branch, change no behaviour, use the layers api, application, domain and infrastructure, and run the service's component and contract suites before and after. `unit-tests.mdc` has the glob for the service unit-test directories (`**/tests/unit/**`): write pure-function tests with pytest-mock `autospec=True`, no database, Kafka, Redis or HTTP, and `.build()` factories only. `python-style.mdc` already covers production code.