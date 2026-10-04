# P3 - Component tests (task-service fully first)
Each sub-task = new chat. Attach: cat-component.md (the service's line), SUT_MAP.md, the service's route/deps files.
- P3.1 task-service: full catalogue list. Bugs -> xfail(strict) + KNOWN_ISSUES.md.
- P3.2 auth-service: replicate the structure of P3.1.
- P3.3 api-gateway: respx upstreams, JWT matrix.
- P3.4 webhook-receiver + external-service-simulator.
- P3.5 webhook-dispatcher + notification-worker: worker components; patch asyncio.sleep/jitter. Coupled to internal functions: do it after the worker refactor (p10, section F) or cover the behaviour black-box in integration (S1-S4) first.
- P3.6 scheduler-worker: real PG for cleanup (clean_db); respx for replay. Same note: after the scheduler refactor; meanwhile cover cleanup and DLQ replay in integration with the shortened timing knobs.
DoD each: `make t-component SERVICE=<x>` green 3x random order, -n auto; coverage of the service's routes/services printed (--cov=<service path>).
