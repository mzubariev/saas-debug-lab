/**
 * spike_traffic.js — Sudden traffic spike scenario
 *
 * PURPOSE
 *   Open-loop spike against the real nginx api zone: 20 r/s, burst 100,
 *   excess delayed (no nodelay), keyed by Authorization. setup() shares one
 *   token, so every VU is one bucket. Each iteration is one GET /tasks plus
 *   a 30% POST /tasks (~1.3 HTTP calls).
 *     - baseline ~12 iter/s ≈ 16 r/s (under the bucket)
 *     - spike ~46 iter/s ≈ 60 r/s (about 3x)
 *     - 429s are expected and are not http_req_failed
 *     - latency Trends record 200/201 only
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
 *   list_tasks_ms and create_task_ms include only status 200/201.
 */

import http from 'k6/http'
import { check, group, sleep } from 'k6'
import { Counter, Trend } from 'k6/metrics'
import {
  login,
  randomTitle,
  listTasks,
  createTask,
  reqTags,
  trackOutcome,
} from '../lib/helpers.js'

http.setResponseCallback(http.expectedStatuses({ min: 200, max: 299 }, 429))

const SCENARIO = 'spike_traffic'

// ─── Custom metrics ────────────────────────────────────────────────────────
const rateLimited = new Counter('rate_limited_requests')
const taskCreateOk = new Counter('tasks_created_ok')
const otherStatus = new Counter('non_success_status')
const listLatency = new Trend('list_tasks_ms', true)
const createLatency = new Trend('create_task_ms', true)

// ─── Test configuration ────────────────────────────────────────────────────
export const options = {
  scenarios: {
    spike: {
      executor: 'ramping-arrival-rate',
      startRate: 5,
      timeUnit: '1s',
      preAllocatedVUs: 80,
      maxVUs: 400,
      stages: [
        { duration: '20s', target: 12 },
        { duration: '15s', target: 46 },
        { duration: '60s', target: 46 },
        { duration: '30s', target: 12 },
        { duration: '60s', target: 12 },
      ],
    },
  },

  thresholds: {
    http_req_failed: ['rate<0.05'],
    list_tasks_ms: ['p(95)<800'],
    create_task_ms: ['p(95)<1500'],
    checks: ['rate>0.99'],
  },
}

// ─── One-time setup ────────────────────────────────────────────────────────
export function setup() {
  const session = login('admin', 'admin123', reqTags(SCENARIO, 'login'))
  if (!session) throw new Error('Setup failed: could not obtain JWT')
  return { token: session.token }
}

// ─── Main VU loop ──────────────────────────────────────────────────────────
export default function (data) {
  const tGet = reqTags(SCENARIO, 'get_tasks')
  const tCreate = reqTags(SCENARIO, 'create_task')

  group('list_tasks', () => {
    const res = listTasks(data.token, tGet)

    if (res.status === 429) {
      rateLimited.add(1)
      return
    }
    trackOutcome(res, listLatency, otherStatus)

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

      if (res.status === 429) {
        rateLimited.add(1)
        return
      }
      trackOutcome(res, createLatency, otherStatus)
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
