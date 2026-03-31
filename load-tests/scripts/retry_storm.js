/**
 * retry_storm.js — Webhook failure cascade and DLQ retry behaviour
 *
 * RUN
 *   k6 run load-tests/scripts/retry_storm.js
 *   k6 run -e FAIL_RATE=0.9 load-tests/scripts/retry_storm.js
 */

import { check, group, sleep } from 'k6'
import { Counter, Rate } from 'k6/metrics'
import {
  login,
  randomTitle,
  createTask,
  sendWebhook,
  simulateWebhookReceive,
  reqTags,
} from '../lib/helpers.js'

const SCENARIO_ORGANIC = 'retry_storm_organic'
const SCENARIO_DIRECT = 'retry_storm_direct'
const SCENARIO_SIM = 'retry_storm_simulator'

// ─── Custom metrics ────────────────────────────────────────────────────────
const webhookAccepted = new Counter('webhook_accepted_202')
const webhookFailed = new Counter('webhook_endpoint_errors')
const taskCreated = new Counter('tasks_created_for_events')
const simFailures = new Counter('simulator_direct_failures')
const simFailRate = new Rate('simulator_fail_rate')

const FAIL_RATE = parseFloat(__ENV.FAIL_RATE || '0.9')

// ─── Test configuration — two parallel scenarios ──────────────────────────
export const options = {
  scenarios: {
    organic_task_events: {
      executor: 'constant-vus',
      vus: 5,
      duration: '3m',
      exec: 'organicFlow',
      gracefulStop: '10s',
    },

    direct_webhook_flood: {
      executor: 'constant-vus',
      vus: 5,
      duration: '3m',
      exec: 'directFlow',
      gracefulStop: '10s',
    },

    simulator_baseline: {
      executor: 'constant-vus',
      vus: 2,
      duration: '3m',
      exec: 'simulatorBaseline',
      gracefulStop: '10s',
    },
  },

  thresholds: {
    http_req_failed: ['rate<0.10'],
    'http_req_duration{endpoint:create_task}': ['p(95)<2000'],
    'http_req_duration{endpoint:webhooks_send}': ['p(95)<1500'],
    'http_req_duration{endpoint:simulator_receive_webhook}': ['p(95)<3000'],
    webhook_endpoint_errors: ['count<30'],
  },
}

// ─── Shared setup ─────────────────────────────────────────────────────────
export function setup() {
  const token = login('admin', 'admin123', reqTags('retry_storm', 'login'))
  if (!token) throw new Error('Setup failed: could not obtain JWT')
  console.log(
    `[retry_storm] configured FAIL_RATE=${FAIL_RATE}. ` +
      `Ensure external-service-simulator DEFAULT_FAIL_RATE >= ${FAIL_RATE} for end-to-end testing.`,
  )
  return { token }
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

export function directFlow(data) {
  group('direct_webhook_send', () => {
    const res = sendWebhook(
      'load_test.retry_storm',
      {
        source: 'k6',
        timestamp: Date.now(),
        iteration: __ITER,
      },
      reqTags(SCENARIO_DIRECT, 'webhooks_send'),
    )

    if (res.status === 202) {
      webhookAccepted.add(1)
    } else {
      webhookFailed.add(1)
    }

    check(res, { 'direct send: 202 accepted': r => r.status === 202 })
  })

  sleep(0.3)
}

export function simulatorBaseline() {
  group('simulator_direct', () => {
    const res = simulateWebhookReceive(
      'load_test.baseline',
      { source: 'k6', vu: __VU },
      FAIL_RATE,
      0,
      reqTags(SCENARIO_SIM, 'simulator_receive_webhook'),
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
