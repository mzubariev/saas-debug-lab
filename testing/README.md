# saas-testkit

Installable test kit for saas-debug-lab (`src/saas_testkit`).

From the repo root: `make t-unit`, `make t-check`, `make t-gate LAYER=unit`.
`make deps-up` starts throwaway Postgres, Redis, and Redpanda.
Before a component or contract session, install that service's group:
`cd testing && uv sync --group <service>` or `uv sync --all-groups`.

Adapters are concrete classes. A `Protocol` appears only when a boundary has two implementations.
The same flow runs at component and integration level. The injected `httpx.AsyncClient` transport is the swap point.

Tests run on Python 3.14 with `uv.lock`. Service images still run Python 3.11 with unpinned `requirements.txt`. That gap closes in R0.

## Branch protection

The required status check is `ci-gate` only.

- `ci-gate` uses `if: always()`. A skipped required check counts as passing, so the gate itself has to run and read every needed job.
- A needed job passes when its result is `success` or `skipped`. `failure` and `cancelled` fail the gate.
- `needs` is passed through `env`. It is not interpolated into the script.
- A new job is added to `ci-gate.needs`. Jobs that build or start the stack need `build`, or the cheap jobs `lint`, `security`, and `unit`, so a broken build stops them early. `smoke` is a step inside `integration`, not a separate job.
- Personal-account repositories have no merge queue. Do not add `merge_group`.
