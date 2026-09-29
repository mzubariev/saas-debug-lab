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
 *   Redis cache         : CLI  (Redis CLI -> tasks:list key TTL)
 *   Kafka throughput    : http://localhost:8080  (Kafka UI → task_created topic)
 *   Traces              : http://localhost:16686 (Jaeger → task-service spans)
 *   Metrics             : http://localhost:9090  (Prometheus → http_requests_total)
 *
 * THRESHOLDS
 *   Per-endpoint latency applies to all tagged requests (including 429s, which are fast).
 *   Primary SLO signals remain custom Trends (list_tasks_ms, create_task_ms).
 */

import { check, group, sleep } from 'k6'
import { Counter, Trend } from 'k6/metrics'
import {
  login,
  randomTitle,
  listTasks,
  createTask,
  reqTags,
} from '../lib/helpers.js'

const SCENARIO = 'spike_traffic'

// ─── Custom metrics ────────────────────────────────────────────────────────
const rateLimited = new Counter('rate_limited_requests')
const taskCreateOk = new Counter('tasks_created_ok')
const listLatency = new Trend('list_tasks_ms', true)
const createLatency = new Trend('create_task_ms', true)

// ─── Test configuration ────────────────────────────────────────────────────
export const options = {
  stages: [
    { duration: '20s', target: 10 },
    { duration: '15s', target: 150 },
    { duration: '60s', target: 150 },
    { duration: '30s', target: 10 },
    { duration: '60s', target: 10 },
  ],

  thresholds: {
    http_req_failed: ['rate<0.40'],
    'http_req_duration{endpoint:get_tasks}': ['p(95)<800'],
    'http_req_duration{endpoint:create_task}': ['p(95)<1500'],
    'list_tasks_ms': ['p(95)<800'],
    'create_task_ms': ['p(95)<1500'],
  },
}

// ─── One-time setup ────────────────────────────────────────────────────────
export function setup() {
  const token = login('admin', 'admin123', reqTags(SCENARIO, 'login'))
  if (!token) throw new Error('Setup failed: could not obtain JWT')
  return { token }
}

// ─── Main VU loop ──────────────────────────────────────────────────────────
export default function (data) {
  const tGet = reqTags(SCENARIO, 'get_tasks')
  const tCreate = reqTags(SCENARIO, 'create_task')

  group('list_tasks', () => {
    const res = listTasks(data.token, tGet)
    listLatency.add(res.timings.duration)

    if (res.status === 429) {
      rateLimited.add(1)
      return
    }

    check(res, {
      'list: status 200': r => r.status === 200,
      'list: body is array': r => {
        try {
          return Array.isArray(JSON.parse(r.body))
        } catch {
          return false
        }
      },
    })
  })

  if (Math.random() < 0.30) {
    group('create_task', () => {
      const res = createTask(data.token, randomTitle(), tCreate)
      createLatency.add(res.timings.duration)

      if (res.status === 429) {
        rateLimited.add(1)
        return
      }
      if (res.status === 201) taskCreateOk.add(1)

      check(res, {
        'create: status 201': r => r.status === 201,
        'create: has id': r => {
          try {
            return !!JSON.parse(r.body).id
          } catch {
            return false
          }
        },
      })
    })
  }

  sleep(0.1)
}

export function teardown() {
  console.log(`[spike_traffic] teardown (rate_limited counter: ${rateLimited.name})`)
}
