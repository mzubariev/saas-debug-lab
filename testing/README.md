# saas-testkit

Installable test kit for saas-debug-lab (`src/saas_testkit`).

From the repo root: `make t-unit`, `make t-check`, `make t-gate LAYER=unit`.
`make deps-up` starts throwaway Postgres, Redis, and Redpanda.
Before a component or contract session, install that service's group:
`cd testing && uv sync --group <service>` or `uv sync --all-groups`.

Adapters are concrete classes. A `Protocol` appears only when a boundary has two implementations.
The same flow runs at component and integration level. The injected `httpx.AsyncClient` transport is the swap point.

Tests run on Python 3.14 with `uv.lock`. Service images still run Python 3.11 with unpinned `requirements.txt`. That gap closes in R0.

## Environments

| Environment | What runs | Which tests |
| --- | --- | --- |
| dev | `infra/docker-compose.yml`, project `infra` (the directory name). Fixed `container_name`. Host ports 80 (nginx), 5173 (frontend), 8000 (simulator). | Not the pytest stack. |
| test-stack | `docker-compose.yml` + `docker-compose.test.yml` + `docker-compose.test.ports.yml`, project `saas-test` (`-p saas-test`). `down -v` removes only that project's volumes. Lab host ports are cleared (`!reset`) and republished: nginx `9080`, frontend `5174`, simulator `8002`, mailhog `8026`, toxiproxy `8475`. | `tests/integration` (`make t-int`), `tests/e2e_ui` (`make t-ui`). `UI_URL` is the published frontend, default `http://127.0.0.1:5174`. |
| in-process | One service in-process. Postgres, Redis, and Redpanda from `make deps-up` (`testing/compose.deps.yml`) or Testcontainers. | `tests/unit` (kit only, no services), `tests/component`, `tests/contract`. |
| CI | GitHub Actions starts the test stack as project `saas-test` and sets `BASE_URL`. | integration, ui-e2e, the smoke step on that stack, nightly. |
| any-URL | Nothing is started. `SMOKE_BASE_URL` for smoke. `BASE_URL` for synthetic. Set `UI_URL` when the frontend is not the test stack. | `tests/smoke`, `tests/synthetic`. |

The Grafana synthetic probe and `testing/synthetic/compose.probe.yml` join the dev lab network `infra_default` and call `http://nginx`. That targets the dev lab on purpose.

## Branch protection

The required status check is `ci-gate` only.

- `ci-gate` uses `if: always()`. A skipped required check counts as passing, so the gate itself has to run and read every needed job.
- A needed job passes when its result is `success` or `skipped`. `failure` and `cancelled` fail the gate.
- `needs` is passed through `env`. It is not interpolated into the script.
- A new job is added to `ci-gate.needs`. Jobs that build or start the stack need `build`, or the cheap jobs `lint`, `security`, and `unit`, so a broken build stops them early. `smoke` is a step inside `integration`, not a separate job.
- Personal-account repositories have no merge queue. Do not add `merge_group`.
