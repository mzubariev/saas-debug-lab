# P4: Contract tests
Attach: `design/cat-contract.md`, `SUT_MAP.md`, the `sut/<service>.md` of each service under test, `KIT_MAP.md` and `design/arch-quality.md` (only the Schemathesis row of section 11).

- P4.1 contract/events: test the Envelope and payload schemas, the JSON-schema snapshots, the legacy-to-unknown mapping, and that events captured from the producers validate (captured through `KafkaEventReader` on Redpanda).
- P4.2 contract/http: test OpenAPI validity, exact committed snapshots (ADR-17; use `make contracts-update` for explicit updates), Schemathesis per service (the `SCHEMA_EXAMPLES` environment variable sets the example count), and consumer-side `model_validate` of real responses. A 500 is never filtered away: mark it `xfail(strict)` and add a `KNOWN_ISSUES.md` entry.

Definition of done: `make t-contract SERVICE=<x>` is green for task, auth, webhook-receiver, simulator and gateway.

Time-box: if Schemathesis is blocked after 30 minutes, follow the fallback in `arch-quality.md` section 11.
