# Test catalogue: component

Characterise first; record surprises in KNOWN_ISSUES.md. Bugs -> xfail(strict). Real names from SUT_MAP.

Principle: assert each behaviour at the lowest layer that can observe it. Component owns business behaviour per service. Out of this layer: payload JSON-schema checks and OpenAPI shape (contract), /health and /metrics reachability (smoke), cross-service side effects (integration). Event checks here only assert that an event with the own id/status arrived.
Tiers: T1 = must, T2 = if time, T3 = not planned.

## task-service (the deep showcase)

T1:

- create: 201, `status=created`, `task_created` event with the own id/title.
- validation: empty / oversize / wrong-type title -> 422 (parametrized; an oversize title that gives 500 is a BUG candidate).
- get: 200, 404, bad uuid 422.
- state machine via PATCH `/tasks/{id}/start` and `/complete`: created -> in_progress -> completed; 409 for every illegal transition (one parametrized matrix; message from SUT_MAP); 404 unknown id; `task_updated` event on each transition.
- cache: second GET served from Redis (`tasks:{id}`), invalidated on transition; list cache `tasks:list` invalidated on create. TTL values are not tested.
- Redis down (patched) -> falls through to DB.
- Kafka publish failure -> characterise (the row is committed, the response is an error, the cache is not invalidated: BUG candidate).
- race: N concurrent `start` on one task -> exactly one success.

T3: health/ready/metrics (smoke).

## auth-service

T1:

- token OK for both roles; claims `sub`/`role`/`exp`, lifetime from env.
- wrong password and unknown user -> 401 with the same body; missing fields -> 422.
- `/auth/me`: valid; expired, tampered signature, `alg=none`, missing and malformed header (one parametrized test).
- no password or hash in any response; stored hash is argon2.
- `/ready` stays 200 with dependencies down: characterise as a hazard (one test). 
- user cache hit on the second login (characterise that the cache holds `hashed_password`: BUG candidate); Redis down -> login still works; `/auth/me` makes no database read.
Note: `role` is never enforced anywhere (gateway verifies only, task-service has no JWT check): characterise, there is no authZ matrix to test.



## api-gateway (respx upstreams)

T1:

- routing per prefix `/auth`, `/tasks`, `/webhooks` (parametrized).
- JWT required for `/tasks*` only: 401 missing / invalid / expired, bodies from SUT_MAP (parametrized); `/auth/*` and `/webhooks/*` open.
- header handling: `host`, `sentry-trace`, `baggage`, `traceparent`, `tracestate` are not forwarded; others are.
- upstream 5xx and 4xx passthrough (status and body); timeout -> 504 `Downstream timeout`; connection error -> 502 `Downstream unavailable`.
- CORS: `CORSMiddleware` allows `http://localhost:5173`, `http://127.0.0.1:5173`, and `http://localhost`.
T3: health/metrics (smoke); duplicate operation IDs in OpenAPI (a snapshot already pins them).



## webhook-receiver

T1: valid inbound -> `webhook_inbound` envelope with the own `event`/`data`; invalid body -> 422; producer failure -> 5xx.
T2: `trace_id` propagation (only if the code propagates it; otherwise skip).

## external-service-simulator

T1: idempotency dedupe (same key twice -> `duplicate`; a failed attempt is not recorded).

## webhook-dispatcher, notification-worker, scheduler-worker

**T3 now: deferred to the refactoring phase (F)**, because the tests are coupled to internals that the refactor changes, and the behaviour is covered black-box by integration S1, S2a, S2b, S6. Behaviour list for F, so nothing is lost:

- dispatcher: envelope decode; `Idempotency-Key = payload.id`; 5xx / network retried up to `MAX_RETRIES` with sleeps 1*2^(n-1) s plus 0..+10 % jitter (two sleeps with the defaults; patch `asyncio.sleep` and jitter); 4xx not retried; exhausted -> `webhook.dlq` (a DLQ produce error is logged and swallowed); legacy raw JSON handled; poison message skipped.
- notification-worker: MIME multipart with the task title; SMTP failures counted and swallowed; legacy message.
- scheduler-worker: `cleanup_old_tasks` on real PG (only `completed`, `updated_at < now - CLEANUP_COMPLETED_TASKS_MINUTES`, boundary, `0` disables, in_progress untouched); `retry_failed_webhooks` (DLQ -> HTTP replay, offsets auto-committed, no `Idempotency-Key`, Celery retries only `httpx.RequestError`, any `HTTPStatusError` is final).

