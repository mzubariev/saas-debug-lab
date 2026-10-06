# saas-testkit

Installable test kit for saas-debug-lab (`src/saas_testkit`).

From the repo root: `make t-unit`, `make t-check`, `make t-gate LAYER=unit`.
`make deps-up` starts throwaway Postgres, Redis, and Redpanda.
Before a component or contract session, install that service's group:
`cd testing && uv sync --group <service>` or `uv sync --all-groups`.

Adapters are concrete classes. A `Protocol` appears only when a boundary has two implementations.
The same flow runs at component and integration level. The injected `httpx.AsyncClient` transport is the swap point.

Tests run on Python 3.14 with `uv.lock`. Service images still run Python 3.11 with unpinned `requirements.txt`. That gap closes in R0.
