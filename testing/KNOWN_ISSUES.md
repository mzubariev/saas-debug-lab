# Known issues

## Defects

## Testability changes

- `infra/docker-compose.datadog.yml`, service `requirements.txt`, `saas_shared.logging`, `saas_shared.sentry_setup`, `saas_shared.telemetry`: removed Datadog (`ddtrace-run`, the `ddtrace` requirement, the log processor, and the Sentry hooks) so a missing package does not stamp `dd_trace_error` on every log line.

## Decisions since the plan
