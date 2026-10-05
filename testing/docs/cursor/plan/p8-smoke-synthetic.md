# P8: Smoke and synthetic checks
Attach: `design/cat-smoke-synthetic.md` and `KIT_MAP.md`.

## P8.1 smoke
Write `tests/smoke/` from the catalogue. It reads `SMOKE_BASE_URL`. Add `make t-smoke` and `.github/workflows/smoke.yml` (`workflow_call` and `workflow_dispatch`; CI reuses it after the stack is up).
Definition of done: `SMOKE_BASE_URL=http://localhost make t-smoke` is green, and a wrong URL fails fast with a clear message.

## P8.2 synthetic
Write `tests/synthetic/api/test_critical_path.py` (and optionally `browser/`) from the catalogue: a dedicated synthetic user from the environment, the `X-Synthetic: true` header, per-step latency budgets (soft warning, hard failure), and step timings in JUnit and the job summary. Add `make t-synthetic`. Add `.github/workflows/synthetic.yml` with `cron */5` (API) and `*/30` (browser) and an issue after three consecutive failures, but keep the schedule commented out and the workflow `workflow_dispatch` only, because the lab is local; enable the cron when a reachable URL exists. Add `make synthetic-local` (a shell loop every five minutes with `SYNTHETIC_BASE_URL=http://localhost`).
Definition of done: `make synthetic-local` runs two cycles green, a deliberately slow step trips the budget, and the workflow lints with `actionlint`.

## P8.3 Grafana Synthetic Monitoring (optional; cut this first)
This is the recommended continuous monitor for the local lab, but it is a stretch goal. Sign up for Grafana Cloud Free and write `testing/synthetic/k6/critical_path.js` (login, create, read; reuse `load-tests/lib/helpers.js`, so un-ignore `load-tests/lib` first). Run a private probe (outbound-only, no tunnel or ngrok) through `testing/synthetic/compose.probe.yml`, following the current Grafana documentation for the agent image and flags. Create the check, an alert and a dashboard. Do not commit tokens.
Definition of done: the check shows green in Grafana Cloud while the lab runs, and stopping task-service turns it red and fires the alert.
