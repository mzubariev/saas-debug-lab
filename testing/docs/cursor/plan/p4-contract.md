# P4 - Contract tests
Attach: cat-contract.md, SUT_MAP.md, arch-quality.md (§11 Schemathesis row only).
- P4.1 contract/events: Envelope + payload schema tests, JSON-schema snapshots, legacy -> unknown, producers' captured events validate (captured through KafkaEventReader on Redpanda).
- P4.2 contract/http: OpenAPI validity, exact committed snapshots (ADR-17, make contracts-update for explicit updates), Schemathesis per service (SCHEMA_EXAMPLES env; a 500 is never filtered away: xfail(strict) + KNOWN_ISSUES.md), consumer-side model_validate of real responses.
DoD: `make t-contract SERVICE=<x>` green for task, auth, webhook-receiver, simulator, gateway.
Time-box: Schemathesis blocked after 30 min -> fallback in arch-quality.md §11.
