# Test catalogue: contract (P4)

## Catalogue
contract/http, per service: OpenAPI valid; committed exact snapshot (any diff fails, ADR-17, principles below); Schemathesis (25-50 examples on PR, 500+ nightly, not_a_server_error + schema conformance); consumer-side Pydantic models validate real responses.
contract/events: Envelope v1 model; payload schema per topic (task_created, task_updated, webhook_inbound, webhook_dlq); JSON-schema snapshots in contracts/events; producers' captured events validate (via KafkaEventReader on Redpanda); legacy -> unknown.

## Contract principles
1. Never silence a 500 in Schemathesis with filters, exclude_*, custom checks that accept it, or by dropping the check. A 5xx on generated input is a defect: the right fix is request validation (422) in the service. Fixing is out of scope in the testing phase (testing-modify-prod.mdc), so record it as xfail(strict=True, reason="BUG-n") for that operation + KNOWN_ISSUES.md; the fix lands in the refactoring phase and the xfail flips to a failure that forces removal.
2. Consumer models are run against real responses: component/contract tests call the endpoint and pass the body through Model.model_validate(...). Response models are tolerant readers (extra="ignore"), request models and envelopes are strict (python-style.mdc).
3. Snapshots are exact (ADR-17): normalised JSON (sort_keys, stable indent, no volatile fields such as servers/build version), one file per service/event; the test diffs the live schema against the committed file and prints a readable diff. Update only via make contracts-update. oasdiff breaking can be added later as a nightly stretch if "additive = ok" is ever needed.
4. The contract layer asserts shape, not behaviour: business rules belong to component tests.
