# Grafana Cloud Synthetic Monitoring (private probe, API)

The check is `k6/critical_path.js`: login, create a `synthetic-` task, read it, start it, and complete it. Completing the task lets the scheduler delete it (cleanup removes completed tasks only; one left in `created` would accumulate on every 5-minute run). It also runs on the host with `k6 run` and a local secret source (below). The probe container is outbound only and shares the lab network (`infra_default`), so the check's `BASE_URL` inside Grafana is `http://nginx`.

## Grafana Cloud setup

1. Sign up for Grafana Cloud on the Free plan and open the stack.
2. Install Synthetic Monitoring (Testing & synthetics) if the stack does not already have it.
3. Go to Testing & synthetics > Synthetics > Probes > Add Private Probe. Save a name, latitude, longitude, and region. Copy the Probe Authentication Token. It is shown once.
4. On the Synthetic Monitoring config page, copy the Probe API Server URL for the stack region. Leave off `https://`.
5. `cp testing/synthetic/.env.example testing/synthetic/.env` and set `API_TOKEN` and `API_SERVER`.
6. From the repo root: `docker compose -f testing/synthetic/compose.probe.yml up -d`. The probe shows on the Probes page. The image is the current stable release `grafana/synthetic-monitoring-agent:v0.66.1` (not the `-browser` tag; this check is API only) with `--api-server-address`, `--api-token`, and `--verbose=true`.
7. Create a Scripted check. Paste `testing/synthetic/k6/critical_path.js`. Scripted checks cannot import files from this repo.
8. Create secrets `synthetic-user` and `synthetic-password` at Testing & synthetics > Synthetics > Config > Secrets. Scripted checks support `k6/secrets`: the script calls `await secrets.get` inside the default function. Set the check variable `BASE_URL` = `http://nginx` only. Choose this private probe. Frequency 5 minutes stays inside a free-plan budget for one probe.
9. Seed that user once on the lab database before the first run: `SYNTHETIC_USER=... SYNTHETIC_PASSWORD=...` and `uv run python -c "from saas_testkit.infra import seed_synthetic_user; seed_synthetic_user()"` from `testing/`. An existing username is left as-is. The seed still reads those environment variables. The k6 script does not.
10. On the host, `k6 run` cannot use the Grafana Cloud secret source (that source is `k6 cloud run --local-execution` only, and it errors under `k6 run`). Pass a local source, and do not commit the file:

```
k6 run -e BASE_URL=http://localhost --secret-source=file=/path/to/secrets.txt testing/synthetic/k6/critical_path.js
```

`secrets.txt` is two lines, `synthetic-user=...` and `synthetic-password=...`. `--secret-source=mock=synthetic-user=...,synthetic-password=...` is the other source from the manage-secrets doc.
11. On the check, enable alerting. Turn on the built-in failed-execution rule (per-check "failed checks", and the legacy `probe_success` rules in the `synthetic_monitoring` namespace). The per-check latency control in the docs applies to HTTP, DNS, and Ping checks. This scripted check fails its own step thresholds (`http_req_duration` p(95) under 3s), and that failed execution is what the failed-execution rule alerts on. For a separate latency page, add a Grafana-managed rule on `probe_http_duration_seconds` or `probe_all_duration_seconds` as in the custom-alerts doc.
12. Alerting > Contact points: add an email contact point and route the `synthetic_monitoring` namespace to it.

## What the preset dashboards show

The Synthetic Monitoring screens graph whether executions passed (`probe_success`, `probe_all_success`) and how long they took (`probe_all_duration_seconds`). The check page lists each execution and its logs.

## Dashboard panels

Build these three panels. `step` is `login`, `create`, `read`, `start`, or `complete`.

- Success by step: `probe_check_success_rate` (label `step`; label `check` is the assertion name).
- p95 latency by step: `probe_http_duration_seconds` (label `step`, split by `phase`). The scripted-check docs attach request tags to this metric, and also to `probe_http_status_code`, `probe_http_info`, and `probe_http_requests_total`. Whole-request time is the histogram `probe_http_total_all_duration_seconds` (k6 `http_req_duration`); those docs do not list `step` on it.
- Uptime: `probe_success` (`1` passed, `0` failed).

## Prove it

With the probe running and the check green, `docker stop task-service`. The next execution fails on create or read, the check turns red, and the failed-execution alert emails the contact point. `docker start task-service` clears it after a following execution passes.

Free plan limits: verify on the pricing page.
