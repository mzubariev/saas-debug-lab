/**
 * Shared helpers for all k6 load-test scripts.
 *
 * Import example:
 *   import { login, authHeaders, randomTitle, randomItem } from '../lib/helpers.js'
 */
import http  from 'k6/http'
import { check } from 'k6'

// ─── Base URLs ────────────────────────────────────────────────────────────────
// Override via k6 env:
//   k6 run -e BASE_URL=http://localhost scripts/spike_traffic.js
export const BASE_URL          = __ENV.BASE_URL          || 'http://localhost'
export const WEBHOOK_SIM_URL   = __ENV.WEBHOOK_SIM_URL   || 'http://localhost:8004'

// ─── Auth ─────────────────────────────────────────────────────────────────────
/**
 * POST /auth/token and return the JWT access_token string.
 * Returns null and logs on failure — callers should bail out if null.
 */
export function login(username = 'admin', password = 'admin123') {
  const res = http.post(
    `${BASE_URL}/auth/token`,
    { username, password },                          // k6 encodes as form-urlencoded
    { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
  )
  const ok = check(res, { 'setup: login 200': r => r.status === 200 })
  if (!ok) {
    console.error(`[login] failed — status=${res.status} body=${res.body}`)
    return null
  }
  return res.json('access_token')
}

/**
 * Return request headers with a Bearer token and JSON content-type.
 */
export function authHeaders(token) {
  return {
    Authorization:  `Bearer ${token}`,
    'Content-Type': 'application/json',
  }
}

// ─── Task helpers ─────────────────────────────────────────────────────────────
const _VERBS = [
  'Implement', 'Configure', 'Deploy', 'Fix', 'Investigate',
  'Monitor',   'Optimize',  'Review', 'Update',  'Harden',
  'Migrate',   'Document',  'Test',   'Benchmark', 'Refactor',
]
const _COMPONENTS = [
  'auth service',        'task service',         'Kafka consumer group',
  'Redis cache layer',   'Postgres index',       'API gateway routing',
  'Nginx rate limiter',  'Celery beat schedule', 'webhook retry logic',
  'notification pipeline','Jaeger trace sampling','Prometheus scrape config',
  'Grafana dashboard',   'Elasticsearch mapping','CI/CD pipeline',
  'dead-letter queue',   'Toxiproxy chaos rules','Alembic migration',
  'OpenTelemetry span',  'connection pool',
]

/** Generate a realistic-looking random task title. */
export function randomTitle() {
  const verb = randomItem(_VERBS)
  const comp = randomItem(_COMPONENTS)
  return `${verb} ${comp}`
}

/** Pick a random element from an array. */
export function randomItem(arr) {
  return arr[Math.floor(Math.random() * arr.length)]
}

/** Return a random integer in [min, max] (inclusive). */
export function randomIntBetween(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min
}

// ─── HTTP wrappers ────────────────────────────────────────────────────────────
/** GET /tasks — returns parsed body or null. */
export function listTasks(token) {
  return http.get(`${BASE_URL}/tasks`, { headers: authHeaders(token) })
}

/** POST /tasks — returns response. */
export function createTask(token, title) {
  return http.post(
    `${BASE_URL}/tasks`,
    JSON.stringify({ title }),
    { headers: authHeaders(token) },
  )
}

/** GET /tasks/{id} — returns response. */
export function getTask(token, taskId) {
  return http.get(`${BASE_URL}/tasks/${taskId}`, { headers: authHeaders(token) })
}

/** PATCH /tasks/{id}/start — returns response. */
export function startTask(token, taskId) {
  return http.patch(
    `${BASE_URL}/tasks/${taskId}/start`,
    null,
    { headers: authHeaders(token) },
  )
}

/** PATCH /tasks/{id}/complete — returns response. */
export function completeTask(token, taskId) {
  return http.patch(
    `${BASE_URL}/tasks/${taskId}/complete`,
    null,
    { headers: authHeaders(token) },
  )
}

/** POST /webhooks/send — fire-and-forget outbound webhook (no auth required). */
export function sendWebhook(event, data = {}) {
  return http.post(
    `${BASE_URL}/webhooks/send`,
    JSON.stringify({ event, data }),
    { headers: { 'Content-Type': 'application/json' } },
  )
}

/** POST directly to webhook-simulator /receive-webhook with fail_rate override. */
export function simulateWebhookReceive(event, data = {}, failRate = 0.0, delaySeconds = 0) {
  const url = `${WEBHOOK_SIM_URL}/receive-webhook?fail_rate=${failRate}&delay=${delaySeconds}`
  return http.post(
    url,
    JSON.stringify({ event, data }),
    { headers: { 'Content-Type': 'application/json' } },
  )
}

/** POST /trigger-event to webhook-simulator — simulates inbound push to integration-service. */
export function triggerInboundEvent(event, data = {}) {
  return http.post(
    `${WEBHOOK_SIM_URL}/trigger-event`,
    JSON.stringify({ event, data }),
    { headers: { 'Content-Type': 'application/json' } },
  )
}
