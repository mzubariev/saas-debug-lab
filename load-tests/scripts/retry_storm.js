/**
 * retry_storm.js — Webhook failure cascade and DLQ retry behaviour
 *
 * PURPOSE
 *   Flood the webhook-dispatcher outbound delivery pipeline while the
 *   webhook-simulator is configured to fail at a high rate. This exercises:
 *     - webhook-dispatcher exponential back-off (1 s → 2 s → 4 s)
 *     - Dead-letter queue (webhook_dlq Kafka topic) filling under pressure
 *     - Celery scheduler-worker's retry_failed_webhooks job draining the DLQ
 *     - Notification worker receiving task_created events and sending emails
 *       through Toxiproxy → MailHog
 *
 * PREREQUISITES — set up webhook failures BEFORE running this test:
 *
 *   Option A — restart webhook-simulator with a high default fail rate:
 *     WEBHOOK_SIMULATOR_DEFAULT_FAIL_RATE=0.9 \
 *     docker compose -f infra/docker-compose.yml up -d webhook-simulator
 *
 *   Option B — use Toxiproxy (or similar) to inject network faults; for SMTP
 *              chaos the lab uses the mailhog-smtp proxy — not the webhook path.
 *     curl -s -X POST http://localhost:8474/proxies/mailhog-smtp/toxics \
 *       -H 'Content-Type: application/json' \
 *       -d '{"name":"latency","type":"latency","attributes":{"latency":500,"jitter":200}}'
 *
 * TWO TRAFFIC STREAMS (run concurrently via k6 scenarios)
 *
 *   organic  — Creates tasks via POST /tasks → task_created → webhook-dispatcher
 *              delivers → fails → retry → DLQ.
 *
 *   direct   — POST /webhooks/send → integration-service publishes webhook_dispatch
 *              → webhook-dispatcher delivers (saturates delivery without task CRUD).
 *
 * RUN
 *   k6 run load-tests/scripts/retry_storm.js
 *   # With explicit fail-rate annotation in the output label:
 *   k6 run -e FAIL_RATE=0.9 load-tests/scripts/retry_storm.js
 *
 * WATCH
 *   DLQ depth      : http://localhost:8080  Kafka UI → topic webhook_dlq
 *   Retry jobs     : http://localhost:5555  Flower → retry_failed_webhooks task
 *   Dispatcher log : docker logs webhook-dispatcher --follow
 *                    look for: webhook_attempt_failed, webhook_failed_permanently
 *   Email delivery : http://localhost:8025  MailHog (if Toxiproxy not fully blocking)
 *   Traces         : http://localhost:16686 Jaeger → integration-service (HTTP) if enabled
 */

import http from 'k6/http'
import { check, group, sleep } from 'k6'
import { Counter, Rate } from 'k6/metrics'
import {
  BASE_URL, WEBHOOK_SIM_URL,
  login, randomTitle, createTask, sendWebhook, simulateWebhookReceive,
} from '../lib/helpers.js'

// ─── Custom metrics ────────────────────────────────────────────────────────
const webhookAccepted  = new Counter('webhook_accepted_202')   // HTTP 202 from integration-service (queued)
const webhookFailed    = new Counter('webhook_endpoint_errors')// 4xx/5xx on /webhooks/send
const taskCreated      = new Counter('tasks_created_for_events')
const simFailures      = new Counter('simulator_direct_failures')

// Percentage of direct simulator calls that returned a failure status
const simFailRate      = new Rate('simulator_fail_rate')

const FAIL_RATE = parseFloat(__ENV.FAIL_RATE || '0.9')

// ─── Test configuration — two parallel scenarios ──────────────────────────
export const options = {
  scenarios: {
    // Scenario 1: organic task creation → Kafka → webhook delivery attempt
    organic_task_events: {
      executor:    'constant-vus',
      vus:         5,
      duration:    '3m',
      exec:        'organicFlow',
      gracefulStop: '10s',
    },

    // Scenario 2: direct POST /webhooks/send to saturate the webhook pipeline
    direct_webhook_flood: {
      executor:    'constant-vus',
      vus:         5,
      duration:    '3m',
      exec:        'directFlow',
      gracefulStop: '10s',
    },

    // Scenario 3: direct calls to webhook-simulator to measure raw fail rate
    simulator_baseline: {
      executor:    'constant-vus',
      vus:         2,
      duration:    '3m',
      exec:        'simulatorBaseline',
      gracefulStop: '10s',
    },
  },

  thresholds: {
    // The gateway and integration-service should always accept the request (202)
    // even though the downstream delivery will fail — 202 = "accepted for delivery"
    http_req_failed:          ['rate<0.10'],
    'webhook_endpoint_errors': ['count<30'],
  },
}

// ─── Shared setup ─────────────────────────────────────────────────────────
export function setup() {
  const token = login()
  if (!token) throw new Error('Setup failed: could not obtain JWT')
  console.log(
    `[retry_storm] configured FAIL_RATE=${FAIL_RATE}. ` +
    `Ensure webhook-simulator DEFAULT_FAIL_RATE >= ${FAIL_RATE} for end-to-end testing.`
  )
  return { token }
}

// ─── Scenario: organic task events ────────────────────────────────────────
//
// Creates tasks so task-service emits task_created Kafka events.
// webhook-dispatcher consumes those and attempts webhook delivery.
// With webhook-simulator at high fail_rate, most attempts fail → DLQ.
//
export function organicFlow(data) {
  group('organic_task_create', () => {
    const res = createTask(data.token, `[retry-storm] ${randomTitle()}`)

    if (res.status === 201) {
      taskCreated.add(1)
    }

    check(res, { 'organic create: 201': r => r.status === 201 })
  })

  // Low think time — we want to flood the Kafka topic quickly
  sleep(0.5)
}

// ─── Scenario: direct webhook flood ────────────────────────────────────────
//
// POSTs directly to /webhooks/send, bypassing task creation.
// webhook-dispatcher delivers → fails → retries → DLQ.
// Lets you saturate the webhook pipeline independently of the task event stream.
//
export function directFlow(data) {
  group('direct_webhook_send', () => {
    const res = sendWebhook('load_test.retry_storm', {
      source:    'k6',
      timestamp: Date.now(),
      iteration: __ITER,
    })

    if (res.status === 202) {
      webhookAccepted.add(1)
    } else {
      webhookFailed.add(1)
    }

    check(res, { 'direct send: 202 accepted': r => r.status === 202 })
  })

  sleep(0.3)
}

// ─── Scenario: simulator baseline ─────────────────────────────────────────
//
// Calls the webhook-simulator /receive-webhook endpoint DIRECTLY at the
// configured FAIL_RATE. This gives a baseline measurement of the simulator's
// raw failure behaviour independent of dispatcher retry logic.
// Compare this rate to the DLQ depth you see in Kafka UI.
//
export function simulatorBaseline(data) {
  group('simulator_direct', () => {
    const res = simulateWebhookReceive(
      'load_test.baseline',
      { source: 'k6', vu: __VU },
      FAIL_RATE,
      /* delaySeconds= */ 0,
    )

    const failed = res.status >= 400 || res.status === 0
    simFailRate.add(failed)
    if (failed) simFailures.add(1)

    check(res, {
      'simulator: returned a response': r => r.status > 0,
      // At FAIL_RATE=0.9 we expect ~90% failures — just verify the response shape
      'simulator: valid status':        r => [200, 500, 503].includes(r.status),
    })
  })

  sleep(1)
}
