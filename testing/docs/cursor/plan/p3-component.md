# P3: Component tests (task-service fully first)

Each sub-task is a new chat. Attach: `design/cat-component.md` (the line for that service), `sut/SUT_MAP.md`, `sut/<service>.md`, `KIT_MAP.md` and the service's route and dependency files.

- P3.1 task-service: cover the full catalogue line. Record bugs as `xfail(strict=True)` plus a `KNOWN_ISSUES.md` entry. This is the golden example, so review it yourself.
Optional, only after the P3.1 tests are green: one property-based state-machine test of the task lifecycle with Hypothesis `RuleBasedStateMachine` (Hypothesis is already a transitive dependency through Schemathesis). It generates transition sequences against the real service and complements the parametrised 409 matrix. Its invariant: an allowed transition succeeds, and an illegal one returns 409 without changing the task. Keep it in one file with a small `max_examples` and `deadline=None`.
- P3.2 auth-service: replicate the structure of P3.1.
- P3.3 api-gateway: use `respx` for the upstreams and cover the JWT matrix.
- P3.4 webhook-receiver and external-service-simulator.
- P3.5 webhook-dispatcher and notification-worker: these are worker components; patch `asyncio.sleep` and the jitter. They are coupled to internal functions, so write them after the worker refactoring (section F in `p10-polish-after.md`). Until then, cover their behaviour black-box in the integration scenarios S1 to S4.
- P3.6 scheduler-worker: use real Postgres for the cleanup task (`clean_db`) and `respx` for the replay. The same note applies: write it after the scheduler refactoring, and meanwhile cover cleanup and DLQ replay in integration with the shortened timing knobs.

Definition of done for each: `make t-component SERVICE=<x>` is green three times in random order with `-n auto`, and the coverage of the service's routes and services is printed (`--cov=<service path>`).