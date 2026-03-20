/**
 * spike_traffic.js — Sudden traffic spike scenario
 *
 * PURPOSE
 *   Simulate a burst of traffic that exceeds the Nginx rate limit.
 *   Observe how the system degrades gracefully under sudden load:
 *     - Nginx starts returning 429 Too Many Requests (zone=api: 10 req/s, burst 20)
 *     - Redis absorbs the read pressure (GET /tasks cache-aside, TTL 60s)
 *     - Postgres connection pool stays bounded while write pressure increases
 *     - Kafka producer throughput grows with POST /tasks volume
 *
 * TRAFFIC SHAPE
 *
 *   VUs │                 ┌────────────────────────┐
 *   150 │                 │                        │
 *       │         ramp ───┘                        └─── ramp down
 *    10 │ warmup ─┐                                           ┌─ cool-down
 *     0 ├─────────┴──────────────────────────────────────────┴──────────
 *       0s       20s      35s                     95s        125s       185s
 *
 * RUN
 *   k6 run load-tests/scripts/spike_traffic.js
 *   k6 run -e BASE_URL=http://localhost load-tests/scripts/spike_traffic.js
 *
 * WATCH (open these in parallel)
 *   Nginx rate limiting : k6 output → http_req_failed rate, rate_limited count
 *   Redis cache         : http://localhost:5540  (Redis Insight → tasks:list key TTL)
 *   Kafka throughput    : http://localhost:8080  (Kafka UI → task_created topic)
 *   Traces              : http://localhost:16686 (Jaeger → task-service spans)
 *   Metrics             : http://localhost:9090  (Prometheus → http_requests_total)
 */

import http          from 'k6/http'
import { check, group, sleep } from 'k6'
import { Counter, Rate, Trend } from 'k6/metrics'
import {
  BASE_URL, login, authHeaders, randomTitle,
  listTasks, createTask,
} from '../lib/helpers.js'

// ─── Custom metrics ────────────────────────────────────────────────────────
const rateLimited      = new Counter('rate_limited_requests')   // 429 responses
const taskCreateOk     = new Counter('tasks_created_ok')        // successful 201s
const listLatency      = new Trend('list_tasks_ms', true)       // ms histogram
const createLatency    = new Trend('create_task_ms', true)

// ─── Test configuration ────────────────────────────────────────────────────
export const options = {
  stages: [
    // Warm-up: give the system time to fill the Redis cache before the spike
    { duration: '20s', target: 10  },
    // SPIKE: 0 → 150 VUs in 15 s — intentionally smashes through the rate limit
    { duration: '15s', target: 150 },
    // Hold the spike for 60 s — observe sustained 429 pressure and cache behaviour
    { duration: '60s', target: 150 },
    // Ramp down: traffic drops sharply (mirrors a bot traffic event ending)
    { duration: '30s', target: 10  },
    // Cool-down at normal load: confirm the system recovers cleanly
    { duration: '60s', target: 10  },
  ],

  thresholds: {
    // We tolerate up to 40% failed requests — spike will cause many 429s
    http_req_failed:           ['rate<0.40'],
    // Even under rate limiting, successful requests must be fast
    'list_tasks_ms':           ['p(95)<800'],
    'create_task_ms':          ['p(95)<1500'],
  },
}

// ─── One-time setup ────────────────────────────────────────────────────────
export function setup() {
  const token = login()
  if (!token) throw new Error('Setup failed: could not obtain JWT')
  return { token }
}

// ─── Main VU loop ──────────────────────────────────────────────────────────
export default function (data) {
  const headers = authHeaders(data.token)

  // ── Read path (70% of operations) ───────────────────────────────────────
  group('list_tasks', () => {
    const res = listTasks(data.token)
    listLatency.add(res.timings.duration)

    if (res.status === 429) { rateLimited.add(1); return }

    check(res, {
      'list: status 200':   r => r.status === 200,
      'list: body is array': r => {
        try { return Array.isArray(JSON.parse(r.body)) } catch { return false }
      },
    })
  })

  // ── Write path (30% of operations) ──────────────────────────────────────
  if (Math.random() < 0.30) {
    group('create_task', () => {
      const res = createTask(data.token, randomTitle())
      createLatency.add(res.timings.duration)

      if (res.status === 429) { rateLimited.add(1); return }
      if (res.status === 201)   taskCreateOk.add(1)

      check(res, {
        'create: status 201':    r => r.status === 201,
        'create: has id':        r => {
          try { return !!JSON.parse(r.body).id } catch { return false }
        },
      })
    })
  }

  // Minimal think time — keeps pressure very high at peak VU count
  sleep(0.1)
}

export function teardown(data) {
  console.log(`[spike_traffic] total rate-limited (429) requests: ${rateLimited.name}`)
}
