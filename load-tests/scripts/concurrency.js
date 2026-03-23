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
 * RUN
 *   k6 run load-tests/scripts/concurrency.js
 *   k6 run -e BASE_URL=http://localhost -e VUS=30 load-tests/scripts/concurrency.js
 */

import { check, group, sleep } from 'k6'
import { Counter, Rate, Trend } from 'k6/metrics'
import {
  login,
  randomTitle,
  listTasks,
  createTask,
  getTask,
  startTask,
  completeTask,
  reqTags,
} from '../lib/helpers.js'

const SCENARIO = 'concurrency'

// ─── Custom metrics ────────────────────────────────────────────────────────
const lifecycleCompleted = new Counter('lifecycle_completed')
const lifecycleFailed = new Counter('lifecycle_failed')
const cacheHitRate = new Rate('cache_hint_likely')
const readLatency = new Trend('read_ms', true)
const writeLatency = new Trend('write_ms', true)

const TARGET_VUS = parseInt(__ENV.VUS || '20')

// ─── Test configuration ────────────────────────────────────────────────────
export const options = {
  stages: [
    { duration: '30s', target: TARGET_VUS },
    { duration: '5m', target: TARGET_VUS },
    { duration: '30s', target: 0 },
  ],

  thresholds: {
    http_req_failed: ['rate<0.05'],
    'http_req_duration{endpoint:get_tasks}': ['p(95)<500'],
    'http_req_duration{endpoint:create_task}': ['p(95)<800'],
    'http_req_duration{endpoint:get_task}': ['p(95)<500'],
    'http_req_duration{endpoint:start_task}': ['p(95)<800'],
    'http_req_duration{endpoint:complete_task}': ['p(95)<800'],
    'read_ms': ['p(95)<500', 'p(99)<1000'],
    'write_ms': ['p(95)<1500'],
    lifecycle_failed: ['count<50'],
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
  const { token } = data
  const roll = Math.random()

  if (roll < 0.60) {
    group('list_tasks', () => {
      const res = listTasks(token, reqTags(SCENARIO, 'get_tasks'))
      readLatency.add(res.timings.duration)

      cacheHitRate.add(res.timings.duration < 20)

      check(res, {
        'list: 200': r => r.status === 200,
        'list: non-empty': r => {
          try {
            return JSON.parse(r.body).length > 0
          } catch {
            return false
          }
        },
      })
    })
  } else if (roll < 0.80) {
    group('create_task', () => {
      const res = createTask(token, randomTitle(), reqTags(SCENARIO, 'create_task'))
      writeLatency.add(res.timings.duration)

      check(res, {
        'create: 201': r => r.status === 201,
        'create: id': r => {
          try {
            return !!JSON.parse(r.body).id
          } catch {
            return false
          }
        },
      })
    })
  } else if (roll < 0.90) {
    group('full_lifecycle', () => {
      const createRes = createTask(
        token,
        `[lifecycle] ${randomTitle()}`,
        reqTags(SCENARIO, 'create_task'),
      )
      writeLatency.add(createRes.timings.duration)
      if (!check(createRes, { 'lifecycle create: 201': r => r.status === 201 })) {
        lifecycleFailed.add(1)
        return
      }

      let task
      try {
        task = JSON.parse(createRes.body)
      } catch {
        lifecycleFailed.add(1)
        return
      }

      sleep(0.5)

      const startRes = startTask(token, task.id, reqTags(SCENARIO, 'start_task'))
      writeLatency.add(startRes.timings.duration)
      if (!check(startRes, { 'lifecycle start: 200': r => r.status === 200 })) {
        lifecycleFailed.add(1)
        return
      }

      sleep(0.5)

      const completeRes = completeTask(
        token,
        task.id,
        reqTags(SCENARIO, 'complete_task'),
      )
      writeLatency.add(completeRes.timings.duration)
      if (!check(completeRes, { 'lifecycle complete: 200': r => r.status === 200 })) {
        lifecycleFailed.add(1)
        return
      }

      lifecycleCompleted.add(1)
    })
  } else {
    group('get_single_task', () => {
      const listRes = listTasks(token, reqTags(SCENARIO, 'get_tasks'))
      if (listRes.status !== 200) return

      let tasks
      try {
        tasks = JSON.parse(listRes.body)
      } catch {
        return
      }
      if (!tasks.length) return

      const taskId = tasks[Math.floor(Math.random() * tasks.length)].id
      const getRes = getTask(token, taskId, reqTags(SCENARIO, 'get_task'))
      readLatency.add(getRes.timings.duration)

      check(getRes, {
        'get single: 200': r => r.status === 200,
        'get single: id matches': r => {
          try {
            return JSON.parse(r.body).id === taskId
          } catch {
            return false
          }
        },
      })
    })
  }

  sleep(1)
}
