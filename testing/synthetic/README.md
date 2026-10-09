# Grafana Cloud Synthetic Monitoring (private probe, API)

The check is `k6/critical_path.js`: login, create a `synthetic-` task, read it, start it, and complete it. Completing the task lets the scheduler delete it (cleanup removes completed tasks only; one left in `created` would accumulate on every 5-minute run). It also runs on the host with `k6 run`. The probe container is outbound only and shares the lab network (`infra_default`), so the check's `BASE_URL` inside Grafana is `http://nginx`.

## Grafana Cloud setup

1. Sign up for Grafana Cloud on the Free plan and open the stack.
2. Install Synthetic Monitoring (Testing & synthetics) if the stack does not already have it.
3. Go to Testing & synthetics > Synthetics > Probes > Add Private Probe. Save a name, latitude, longitude, and region. Copy the Probe Authentication Token. It is shown once.
4. On the Synthetic Monitoring config page, copy the Probe API Server URL for the stack region. Leave off `https://`.
5. `cp testing/synthetic/.env.example testing/synthetic/.env` and set `API_TOKEN` and `API_SERVER`.
6. From the repo root: `docker compose -f testing/synthetic/compose.probe.yml up -d`. The probe shows on the Probes page. The image is the current stable release `grafana/synthetic-monitoring-agent:v0.66.1` (not the `-browser` tag; this check is API only) with `--api-server-address`, `--api-token`, and `--verbose=true`.
7. Create a Scripted check. Paste `testing/synthetic/k6/critical_path.js`. Scripted checks cannot import files from this repo.
8. Set the check variables: `BASE_URL` = `http://nginx`, `SYNTHETIC_USER`, `SYNTHETIC_PASSWORD`. Choose this private probe. Frequency 5 minutes stays inside a free-plan budget for one probe.
9. Seed that user once on the lab database before the first run: `SYNTHETIC_USER=... SYNTHETIC_PASSWORD=...` and `uv run python -c "from saas_testkit.infra import seed_synthetic_user; seed_synthetic_user()"` from `testing/`. An existing username is left as-is.
10. On the check, enable alerting. Turn on the built-in failed-execution rule (per-check "failed checks", and the legacy `probe_success` rules in the `synthetic_monitoring` namespace). The per-check latency control in the docs applies to HTTP, DNS, and Ping checks. This scripted check fails its own step thresholds (`http_req_duration` p(95) under 3s), and that failed execution is what the failed-execution rule alerts on. For a separate latency page, add a Grafana-managed rule on `probe_http_duration_seconds` or `probe_all_duration_seconds` as in the custom-alerts doc.
11. Alerting > Contact points: add an email contact point and route the `synthetic_monitoring` namespace to it.

## What the preset dashboards show

The Synthetic Monitoring screens graph whether executions passed (`probe_success`, `probe_all_success`) and how long they took (`probe_all_duration_seconds`, and for this script `probe_http_duration_seconds` and `probe_check_success_rate` with the `step` label: `login`, `create`, `read`, `start`, `complete`). The check page lists each execution and its logs.

## Prove it

With the probe running and the check green, `docker stop task-service`. The next execution fails on create or read, the check turns red, and the failed-execution alert emails the contact point. `docker start task-service` clears it after a following execution passes.

Free plan limits: verify on the pricing page.
