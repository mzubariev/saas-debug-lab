# P6 - Integration stack + tests
Attach: arch-integration.md, SUT_MAP.md.
- P6.1 (strong model): infra/docker-compose.test.yml (gateway published on :8001, WireMock, WEBHOOK_URL of dispatcher AND scheduler -> WireMock, timing knobs, postgres with ADR-18 command + tmpfs; nginx is not relaxed), explicit service list, /health polling, src/saas_testkit/infra/compose.py (BASE_URL env-or-up, KEEP_STACK), seed + login once per run (FileLock, token file with expiry check), adapters: Kafka reader, MailHog, WireMock, real-network HttpTaskApi/HttpAuthApi, tests/integration/conftest.py.
  DoD: `make stack-up` healthy; one test (login -> create task -> task readable) green with -n 3.
- P6.2 integration/services: health via gateway, auth->gateway->task JWT flow, nginx dedicated (serial), /metrics series.
- P6.3 integration/scenarios: S1, S3, S4 first (fast); S2 and S5 marked slow/chaos.
DoD (P6.2-P6.3): `make t-int` green 2x, no test uses sleep, all data unique, works with KEEP_STACK=1.
