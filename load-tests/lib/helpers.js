/**
 * Shared helpers for all k6 load-test scripts.
 *
 * Import example:
 *   import { login, authHeaders, reqTags, randomTitle } from '../lib/helpers.js'
 */
import http from 'k6/http'
import { check } from 'k6'

// ─── Base URLs ────────────────────────────────────────────────────────────────
// Override via k6 env:
//   k6 run -e BASE_URL=http://localhost scripts/spike_traffic.js
export const BASE_URL = __ENV.BASE_URL || 'http://localhost'
export const WEBHOOK_SIM_URL = __ENV.WEBHOOK_SIM_URL || 'http://nginx/external'

// ─── Trace correlation ─────────────────────────────────────────────────────────
/** Unique id per request for log/trace correlation (gateway can forward as X-Request-ID). */
export function requestId() {
  // __VU / __ITER exist only in the default function (per-VU iteration). setup/teardown/init do not define __ITER.
  const vu = typeof __VU !== 'undefined' ? __VU : 'setup'
  const iter = typeof __ITER !== 'undefined' ? __ITER : 0
  return `k6-${vu}-${iter}-${Date.now()}`
}

/** Standard k6 HTTP tags: scenario name + logical endpoint (for thresholds & dashboards). */
export function reqTags(scenario, endpoint) {
  return { scenario, endpoint }
}

// ─── Auth ─────────────────────────────────────────────────────────────────────
/**
 * POST /auth/token and return the JWT access_token string.
 * Returns null and logs on failure — callers should bail out if null.
 * @param {object} [tags] - optional k6 tags e.g. reqTags('my_script', 'login')
 */
export function login(username = 'admin', password = 'admin123', tags) {
  const opts = {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'X-Request-ID': requestId(),
    },
  }
  if (tags) opts.tags = tags

  const res = http.post(
    `${BASE_URL}/auth/token`,
    { username, password },
    opts,
  )
  const ok = check(res, { 'setup: login 200': r => r.status === 200 })
  if (!ok) {
    console.error(`[login] failed — status=${res.status} body=${res.body}`)
    return null
  }
  return res.json('access_token')
}

/**
 * Request headers with Bearer token, JSON content-type, and X-Request-ID.
 */
export function authHeaders(token) {
  return {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
    'X-Request-ID': requestId(),
  }
}

/** JSON POST without Bearer (webhooks, simulator) + X-Request-ID. */
export function anonJsonHeaders() {
  return {
    'Content-Type': 'application/json',
    'X-Request-ID': requestId(),
  }
}

// ─── Task helpers ─────────────────────────────────────────────────────────────
const _VERBS = [
  'Implement', 'Configure', 'Deploy', 'Fix', 'Investigate',
  'Monitor', 'Optimize', 'Review', 'Update', 'Harden',
  'Migrate', 'Document', 'Test', 'Benchmark', 'Refactor',
]
const _COMPONENTS = [
  'auth service', 'task service', 'Kafka consumer group',
  'Redis cache layer', 'Postgres index', 'API gateway routing',
  'Nginx rate limiter', 'Celery beat schedule', 'webhook retry logic',
  'notification pipeline', 'Jaeger trace sampling', 'Prometheus scrape config',
  'Grafana dashboard', 'Elasticsearch mapping', 'CI/CD pipeline',
  'dead-letter queue', 'Toxiproxy chaos rules', 'Alembic migration',
  'OpenTelemetry span', 'connection pool',
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

// ─── HTTP wrappers (tags required at call sites for observability) ─────────────
/** GET /tasks */
export function listTasks(token, tags) {
  return http.get(`${BASE_URL}/tasks`, { headers: authHeaders(token), tags })
}

/** POST /tasks */
export function createTask(token, title, tags) {
  return http.post(`${BASE_URL}/tasks`, JSON.stringify({ title }), {
    headers: authHeaders(token),
    tags,
  })
}

/** GET /tasks/{id} */
export function getTask(token, taskId, tags) {
  return http.get(`${BASE_URL}/tasks/${taskId}`, { headers: authHeaders(token), tags })
}

/** PATCH /tasks/{id}/start */
export function startTask(token, taskId, tags) {
  return http.patch(`${BASE_URL}/tasks/${taskId}/start`, null, {
    headers: authHeaders(token),
    tags,
  })
}

/** PATCH /tasks/{id}/complete */
export function completeTask(token, taskId, tags) {
  return http.patch(`${BASE_URL}/tasks/${taskId}/complete`, null, {
    headers: authHeaders(token),
    tags,
  })
}

/** POST external-service-simulator /receive-webhook */
export function simulateWebhookReceive(
  event,
  data = {},
  failRate = 0.0,
  delaySeconds = 0,
  tags,
) {
  const url = `${WEBHOOK_SIM_URL}/receive-webhook?fail_rate=${failRate}&delay=${delaySeconds}`
  return http.post(url, JSON.stringify({ event, data }), {
    headers: anonJsonHeaders(),
    tags,
  })
}

/** POST external-service-simulator /trigger-event */
export function triggerInboundEvent(event, data = {}, tags) {
  return http.post(`${WEBHOOK_SIM_URL}/trigger-event`, JSON.stringify({ event, data }), {
    headers: anonJsonHeaders(),
    tags,
  })
}
