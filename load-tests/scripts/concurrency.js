/**
 * concurrency.js — Sustained concurrent users (steady-state behaviour)
 *
 * PURPOSE
 *   Simulate realistic production traffic from 20 concurrent users over 5
 *   minutes. Unlike the spike scenario this stays near (not above) the Nginx
 *   rate limit so the focus shifts from rate-limiting to:
 *     - P95 / P99 latency at steady state
 *     - Redis cache-hit ratio stabilising after warm-up
 *     - Full task lifecycle: created → in_progress → completed
 *     - Postgres connection pool staying healthy under sustained writes
 *     - Kafka producer keeping up with the task event stream
 *
 * TRAFFIC MIX  (per iteration)
 *   60% — GET /tasks            (read; should hit Redis cache after warm-up)
 *   20% — POST /tasks           (write; invalidates cache, emits Kafka event)
 *   10% — Full lifecycle        (POST create → PATCH start → PATCH complete)
 *   10% — GET /tasks/{id}       (point read; individual task cache, TTL 120s)
 *
 * TRAFFIC SHAPE
 *
 *   VUs │         ┌─────────────────────────────┐
 *    20 │  ramp ──┘                             └── ramp down
 *     0 ├─────────────────────────────────────────────────
 *       0s       30s                          330s       360s
 *
 * RUN
 *   k6 run load-tests/scripts/concurrency.js
 *   # custom base URL or VU count:
 *   k6 run -e BASE_URL=http://localhost -e VUS=30 load-tests/scripts/concurrency.js
 *
 * WATCH
 *   Latency percentiles  : k6 summary table (http_req_duration p95 / p99)
 *   Cache hit vs miss    : http://localhost:5540 (Redis Insight → tasks:list)
 *   Postgres connections : http://localhost:9090 Prometheus
 *                          query: pg_stat_activity_count (if postgres_exporter is running)
 *   Kafka lag            : http://localhost:8080 (Kafka UI → consumer groups)
 *   Traces               : http://localhost:16686 (Jaeger, filter by service=task-service)
 */

import http from 'k6/http'
import { check, group, sleep } from 'k6'
import { Counter, Rate, Trend } from 'k6/metrics'
import {
  BASE_URL, login, authHeaders, randomTitle,
  listTasks, createTask, getTask, startTask, completeTask,
} from '../lib/helpers.js'

// ─── Custom metrics ────────────────────────────────────────────────────────
const lifecycleCompleted  = new Counter('lifecycle_completed')  // full create→complete cycles
const lifecycleFailed     = new Counter('lifecycle_failed')     // any step that errored
const cacheHitRate        = new Rate('cache_hint_likely')       // proxy: fast list (< 20ms)
const readLatency         = new Trend('read_ms',  true)
const writeLatency        = new Trend('write_ms', true)

const TARGET_VUS = parseInt(__ENV.VUS || '20')

// ─── Test configuration ────────────────────────────────────────────────────
export const options = {
  stages: [
    { duration: '30s',  target: TARGET_VUS },   // ramp up
    { duration: '5m',   target: TARGET_VUS },   // steady state
    { duration: '30s',  target: 0           },  // ramp down
  ],

  thresholds: {
    http_req_failed:    ['rate<0.05'],           // < 5% errors in steady state
    'read_ms':          ['p(95)<500', 'p(99)<1000'],
    'write_ms':         ['p(95)<1500'],
    // Every lifecycle that starts should complete
    lifecycle_failed:   ['count<50'],
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
  const { token } = data
  const roll = Math.random()

  if (roll < 0.60) {
    // ── Path A: List tasks (cache-aside read) ──────────────────────────────
    group('list_tasks', () => {
      const res = listTasks(token)
      readLatency.add(res.timings.duration)

      // A very fast response (< 20 ms) is a strong proxy for a Redis cache hit
      cacheHitRate.add(res.timings.duration < 20)

      check(res, {
        'list: 200':        r => r.status === 200,
        'list: non-empty':  r => {
          try { return JSON.parse(r.body).length > 0 } catch { return false }
        },
      })
    })

  } else if (roll < 0.80) {
    // ── Path B: Create a single task ──────────────────────────────────────
    group('create_task', () => {
      const res = createTask(token, randomTitle())
      writeLatency.add(res.timings.duration)

      check(res, {
        'create: 201':  r => r.status === 201,
        'create: id':   r => {
          try { return !!JSON.parse(r.body).id } catch { return false }
        },
      })
    })

  } else if (roll < 0.90) {
    // ── Path C: Full lifecycle create → in_progress → completed ───────────
    //
    //   This exercises:
    //     1. task-service state machine enforcement
    //     2. Two additional Kafka events (task_updated × 2)
    //     3. Cache invalidation on each state transition
    //
    group('full_lifecycle', () => {
      // Step 1: create
      const createRes = createTask(token, `[lifecycle] ${randomTitle()}`)
      writeLatency.add(createRes.timings.duration)
      if (!check(createRes, { 'lifecycle create: 201': r => r.status === 201 })) {
        lifecycleFailed.add(1); return
      }

      let task
      try { task = JSON.parse(createRes.body) } catch {
        lifecycleFailed.add(1); return
      }

      // Brief pause — mirrors real user behaviour between steps
      sleep(0.5)

      // Step 2: start
      const startRes = startTask(token, task.id)
      writeLatency.add(startRes.timings.duration)
      if (!check(startRes, { 'lifecycle start: 200': r => r.status === 200 })) {
        lifecycleFailed.add(1); return
      }

      sleep(0.5)

      // Step 3: complete
      const completeRes = completeTask(token, task.id)
      writeLatency.add(completeRes.timings.duration)
      if (!check(completeRes, { 'lifecycle complete: 200': r => r.status === 200 })) {
        lifecycleFailed.add(1); return
      }

      lifecycleCompleted.add(1)
    })

  } else {
    // ── Path D: Get a single task by ID  ──────────────────────────────────
    //
    //   Requires a task to already exist (seeded data or from Path B/C above).
    //   First we list to get an ID, then do a point-read to exercise single-task
    //   cache (TTL 120 s, key tasks:{uuid}).
    //
    group('get_single_task', () => {
      const listRes = listTasks(token)
      if (listRes.status !== 200) return

      let tasks
      try { tasks = JSON.parse(listRes.body) } catch { return }
      if (!tasks.length) return

      const taskId = tasks[Math.floor(Math.random() * tasks.length)].id
      const getRes = getTask(token, taskId)
      readLatency.add(getRes.timings.duration)

      check(getRes, {
        'get single: 200':       r => r.status === 200,
        'get single: id matches': r => {
          try { return JSON.parse(r.body).id === taskId } catch { return false }
        },
      })
    })
  }

  // 1-second think time → ~20 VU × 1 req/s ≈ 20 req/s peak (within rate limit)
  sleep(1)
}
