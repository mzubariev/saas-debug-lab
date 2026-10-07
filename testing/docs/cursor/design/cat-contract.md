# Test catalogue: contract (P4)

Tiers: T1 = must, T2 = if time, T3 = not planned. This layer asserts shape, not behaviour; every check here must be something no component test already does.

## Catalogue

### contract/http

T1, per service (task-service, auth-service, webhook-receiver, external-service-simulator, api-gateway):

- OpenAPI document valid.
- committed exact snapshot (any diff fails, ADR-17, principles below).  
T1, Schemathesis (25-50 examples on PR, 500+ nightly, `not_a_server_error` + schema conformance) on **task-service, auth-service, webhook-receiver** only.

- Schemathesis on api-gateway: wildcard proxy routes, no response models, duplicate operation ids; it would test the upstreams, not the gateway.
- Schemathesis on external-service-simulator: a test double that fails on purpose (`fail_rate`, `status`, `delay` are generated query parameters, so 500s and long sleeps are expected behaviour).
- Separate "consumer model validates real response" tests: the flows in component tests already parse every response into the consumer models (tolerant readers).



### contract/events

T1:

- Envelope v1 model (strict) and payload models per topic: `task_created`, `task_updated`, `webhook_inbound`, `webhook_dlq`, with JSON-schema snapshots in `contracts/events` (one file per event).
- legacy / invalid message -> `unknown` (one parametrized test).
- captured producer events validate against the snapshot: one test each for task-service (`task_created`, `task_updated`) and webhook-receiver (`webhook_inbound`), read through `KafkaEventReader` on Redpanda. `webhook_dlq` has no in-process producer; its schema is covered by the model snapshot and integration S2b. 

T3:

- nightly Schemathesis stateful runs. CI: service-agnostic `contract/events` tests run once (not in every matrix leg).



## Contract principles

1. Never silence a 500 in Schemathesis with filters, exclude_*, custom checks that accept it, or by dropping the check. A 5xx on generated input is a defect: the right fix is request validation (422) in the service. Fixing is out of scope in the testing phase (testing-modify-prod.mdc), so record it as xfail(strict=True, reason="BUG-n") for that operation + KNOWN_ISSUES.md; the fix lands in the refactoring phase and the xfail flips to a failure that forces removal.
2. Consumer models are exercised through the flows in component tests (response models are tolerant readers, `extra="ignore"`; request models and envelopes are strict, python-style.mdc).
3. Snapshots are exact (ADR-17): normalised JSON (sort_keys, stable indent, no volatile fields such as servers/build version), one file per service/event; the test diffs the live schema against the committed file and prints a readable diff. Update only via make contracts-update. A dependency bump (FastAPI, Pydantic) can change generated schemas: that diff is reviewed like any other. oasdiff breaking is an optional nightly stretch.
4. The contract layer asserts shape, not behaviour: business rules belong to component tests.

