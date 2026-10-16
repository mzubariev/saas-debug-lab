/**
 * retry_storm.js — Webhook failure cascade and DLQ retry behaviour
 *
 * FAIL_RATE is only the fail_rate query param on direct simulator calls
 * (simulator_baseline). It does not change webhook-dispatcher traffic.
 * Dispatcher posts use the simulator's DEFAULT_FAIL_RATE. Set that on the
 * simulator process before the run if the organic path should fail.
 *
 * RUN
 *   k6 run load-tests/scripts/retry_storm.js
 *   k6 run -e FAIL_RATE=0.9 load-tests/scripts/retry_storm.js
 *
 * Scenarios:
 *   organic_task_events  — POST /tasks → Kafka task_created → webhook-dispatcher → simulator
 *   simulator_baseline   — direct POST /receive-webhook?fail_rate=FAIL_RATE
 *   duplicate_key        — same Idempotency-Key twice, second body status is "duplicate"
 */

import http from 'k6/http'
import { check, group, sleep } from 'k6'
import { Counter, Rate } from 'k6/metrics'
import {
  login,
  floatEnv,
  randomTitle,
  createTask,
  simulateWebhookReceive,
  reqTags,
} from '../lib/helpers.js'

const SCENARIO_ORGANIC = 'retry_storm_organic'
const SCENARIO_SIM = 'retry_storm_simulator'

// ─── Custom metrics ────────────────────────────────────────────────────────
const taskCreated = new Counter('tasks_created_for_events')
const simFailures = new Counter('simulator_direct_failures')
const simFailRate = new Rate('simulator_fail_rate')

// ─── Test configuration ───────────────────────────────────────────────────
export const options = {
  scenarios: {
    organic_task_events: {
      executor: 'constant-vus',
      vus: 5,
      duration: '3m',
      exec: 'organicFlow',
      gracefulStop: '10s',
    },

    simulator_baseline: {
      executor: 'constant-vus',
      vus: 2,
      duration: '3m',
      exec: 'simulatorBaseline',
      gracefulStop: '10s',
    },

    duplicate_key: {
      executor: 'constant-vus',
      vus: 1,
      duration: '3m',
      exec: 'duplicateKey',
      gracefulStop: '10s',
    },
  },

  thresholds: {
    'http_req_duration{endpoint:create_task}': ['p(95)<2000'],
    'http_req_duration{endpoint:simulator_receive_webhook}': ['p(95)<3000'],
    checks: ['rate>0.99'],
  },
}

const CHAOS = __ENV.CHAOS === '1'
if (CHAOS) options.thresholds = {}

// ─── Shared setup ─────────────────────────────────────────────────────────
export function setup() {
  const failRate = floatEnv('FAIL_RATE', 0.9)
  const session = login('admin', 'admin123', reqTags('retry_storm', 'login'))
  if (!session) throw new Error('Setup failed: could not obtain JWT')
  console.log(
    `[retry_storm] FAIL_RATE=${failRate} is the direct-call query param only. ` +
      'Dispatcher traffic uses external-service-simulator DEFAULT_FAIL_RATE.',
  )
  return { token: session.token, failRate }
}

export function organicFlow(data) {
  group('organic_task_create', () => {
    const res = createTask(
      data.token,
      `[retry-storm] ${randomTitle()}`,
      reqTags(SCENARIO_ORGANIC, 'create_task'),
    )

    if (res.status === 201) {
      taskCreated.add(1)
    }

    check(res, { 'organic create: 201': r => r.status === 201 })
  })

  sleep(0.5)
}

export function simulatorBaseline(data) {
  http.setResponseCallback(http.expectedStatuses(200, 500))
  group('simulator_direct', () => {
    const res = simulateWebhookReceive(
      'load_test.baseline',
      { source: 'k6', vu: __VU },
      data.failRate,
      0,
      reqTags(SCENARIO_SIM, 'simulator_receive_webhook'),
      `storm-${__VU}-${__ITER}`,
    )

    const failed = res.status >= 400 || res.status === 0
    simFailRate.add(failed)
    if (failed) simFailures.add(1)

    check(res, {
      'simulator: returned a response': r => r.status > 0,
      'simulator: valid status': r => [200, 500, 503].includes(r.status),
    })
  })

  sleep(1)
}

export function duplicateKey() {
  http.setResponseCallback(http.expectedStatuses(200, 500))
  const key = `dup-${__VU}-${__ITER}-${Date.now()}`
  const tags = reqTags('retry_storm_duplicate', 'simulator_receive_webhook')
  const first = simulateWebhookReceive('load_test.duplicate', { source: 'k6' }, 0, 0, tags, key)
  check(first, {
    'duplicate setup: 200': r => r.status === 200,
    'duplicate setup: stored': r => {
      try {
        return JSON.parse(r.body).status === 'received'
      } catch (e) {
        return false
      }
    },
  })
  const second = simulateWebhookReceive('load_test.duplicate', { source: 'k6' }, 0, 0, tags, key)
  check(second, {
    'duplicate: 200': r => r.status === 200,
    'duplicate: status': r => {
      try {
        return JSON.parse(r.body).status === 'duplicate'
      } catch (e) {
        return false
      }
    },
  })
  sleep(1)
}
