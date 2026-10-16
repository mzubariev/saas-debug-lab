/**
 * Shared helpers for all k6 load-test scripts.
 *
 * Import example:
 *   import { login, getToken, authHeaders, reqTags, randomTitle } from '../lib/helpers.js'
 */
import http from 'k6/http'
import { check } from 'k6'
import encoding from 'k6/encoding'

const TOKEN_TTL_MS = 30 * 60 * 1000
const REFRESH_BEFORE_MS = 2 * 60 * 1000

function stripTrailingSlash(url) {
  return String(url).replace(/\/+$/, '')
}

// ─── Base URLs ────────────────────────────────────────────────────────────────
// Override via k6 env:
//   k6 run -e BASE_URL=http://localhost scripts/spike_traffic.js
export const BASE_URL = stripTrailingSlash(__ENV.BASE_URL || 'http://localhost')
export const WEBHOOK_SIM_URL = stripTrailingSlash(__ENV.WEBHOOK_SIM_URL || 'http://localhost/external')

/**
 * Integer env. Empty means fallback. NaN throws — call from setup().
 * @param {string} name
 * @param {number} fallback
 */
export function intEnv(name, fallback) {
  const raw = __ENV[name]
  if (raw === undefined || raw === '') return fallback
  const n = parseInt(raw, 10)
  if (Number.isNaN(n)) {
    throw new Error(`env ${name} must be an integer, got ${JSON.stringify(raw)}`)
  }
  return n
}

/**
 * Float env. Empty means fallback. NaN throws — call from setup().
 * @param {string} name
 * @param {number} fallback
 */
export function floatEnv(name, fallback) {
  const raw = __ENV[name]
  if (raw === undefined || raw === '') return fallback
  const n = parseFloat(raw)
  if (Number.isNaN(n)) {
    throw new Error(`env ${name} must be a number, got ${JSON.stringify(raw)}`)
  }
  return n
}

// ─── Trace correlation ─────────────────────────────────────────────────────────
let _requestSeq = 0

/** Unique id per call (VU + iteration + counter + random suffix). */
export function requestId() {
  const vu = typeof __VU !== 'undefined' ? __VU : 'setup'
  const iter = typeof __ITER !== 'undefined' ? __ITER : 0
  _requestSeq += 1
  const suffix = Math.random().toString(36).slice(2, 10)
  return `k6-${vu}-${iter}-${_requestSeq}-${suffix}`
}

/** Standard k6 HTTP tags: scenario name + logical endpoint (for thresholds & dashboards). */
export function reqTags(scenario, endpoint) {
  return { scenario, endpoint }
}

function withName(tags, name) {
  return Object.assign({}, tags, { name })
}

// ─── Auth ─────────────────────────────────────────────────────────────────────
/** Per-VU cache. Each VU has its own JS runtime, so this is not shared across VUs. */
let _session = null

function tokenExpMs(token) {
  try {
    const part = token.split('.')[1]
    const payload = JSON.parse(encoding.b64decode(part, 'rawurl', 's'))
    if (typeof payload.exp === 'number') return payload.exp * 1000
  } catch (e) {
    // Fall back to the known access-token TTL.
  }
  return Date.now() + TOKEN_TTL_MS
}

/**
 * POST /auth/token.
 * Returns { token, exp } (exp is epoch ms) or null on failure.
 * @param {string} [username]
 * @param {string} [password]
 * @param {object} [tags]
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
  const token = res.json('access_token')
  if (!token) {
    console.error('[login] 200 without access_token')
    return null
  }
  return { token, exp: tokenExpMs(token) }
}

/**
 * Bearer token for this VU. Re-logins when under 2 minutes remain (TTL is 30 min).
 * @param {string} [username]
 * @param {string} [password]
 * @param {object} [tags]
 */
export function getToken(username = 'admin', password = 'admin123', tags) {
  if (!_session || _session.exp - Date.now() < REFRESH_BEFORE_MS) {
    _session = login(username, password, tags)
    if (!_session) throw new Error('login failed')
  }
  return _session.token
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

/**
 * Add latency to okTrend only for 200/201. Any other status increments otherCounter.
 * @param {object} res
 * @param {object} okTrend k6 Trend
 * @param {object} otherCounter k6 Counter
 */
export function trackOutcome(res, okTrend, otherCounter) {
  if (res.status === 200 || res.status === 201) {
    okTrend.add(res.timings.duration)
    return true
  }
  otherCounter.add(1)
  return false
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
  return http.get(`${BASE_URL}/tasks/${taskId}`, {
    headers: authHeaders(token),
    tags: withName(tags, 'GET /tasks/{id}'),
  })
}

/** PATCH /tasks/{id}/start */
export function startTask(token, taskId, tags) {
  return http.patch(`${BASE_URL}/tasks/${taskId}/start`, null, {
    headers: authHeaders(token),
    tags: withName(tags, 'PATCH /tasks/{id}/start'),
  })
}

/** PATCH /tasks/{id}/complete */
export function completeTask(token, taskId, tags) {
  return http.patch(`${BASE_URL}/tasks/${taskId}/complete`, null, {
    headers: authHeaders(token),
    tags: withName(tags, 'PATCH /tasks/{id}/complete'),
  })
}

/**
 * POST external-service-simulator /receive-webhook.
 * failRate is only the query param on this direct call. Dispatcher traffic
 * uses the simulator process DEFAULT_FAIL_RATE and ignores this value.
 * idempotencyKey is sent as Idempotency-Key (one key per logical event).
 */
export function simulateWebhookReceive(
  event,
  data = {},
  failRate = 0.0,
  delaySeconds = 0,
  tags,
  idempotencyKey,
) {
  const headers = anonJsonHeaders()
  headers['Idempotency-Key'] = idempotencyKey || requestId()
  const url = `${WEBHOOK_SIM_URL}/receive-webhook?fail_rate=${failRate}&delay=${delaySeconds}`
  return http.post(url, JSON.stringify({ event, data }), {
    headers,
    tags,
    responseCallback: http.expectedStatuses(200, 500),
  })
}
