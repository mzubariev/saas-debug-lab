import http from 'k6/http'
import { check } from 'k6'

// One iteration. Grafana SM ignores vus, duration, and iterations.
// http_req_duration is milliseconds. 3000 is under the gateway timeout of 5s.
export const options = {
  thresholds: {
    'checks{step:login}': ['rate==1'],
    'checks{step:create}': ['rate==1'],
    'checks{step:read}': ['rate==1'],
    'checks{step:start}': ['rate==1'],
    'checks{step:complete}': ['rate==1'],
    'http_req_duration{step:login}': ['p(95)<3000'],
    'http_req_duration{step:create}': ['p(95)<3000'],
    'http_req_duration{step:read}': ['p(95)<3000'],
    'http_req_duration{step:start}': ['p(95)<3000'],
    'http_req_duration{step:complete}': ['p(95)<3000'],
  },
}

const baseUrl = (__ENV.BASE_URL || '').replace(/\/$/, '')
const username = __ENV.SYNTHETIC_USER || ''
const password = __ENV.SYNTHETIC_PASSWORD || ''

if (!baseUrl || !username || !password) {
  throw new Error('BASE_URL, SYNTHETIC_USER, and SYNTHETIC_PASSWORD are required')
}

function requestId() {
  const vu = typeof __VU !== 'undefined' ? __VU : 'setup'
  const iter = typeof __ITER !== 'undefined' ? __ITER : 0
  return `k6-${vu}-${iter}-${Date.now()}`
}

function login() {
  const res = http.post(
    `${baseUrl}/auth/token`,
    { username, password },
    {
      headers: { 'X-Request-ID': requestId() },
      tags: { step: 'login' },
    },
  )
  const ok = check(res, { 'login 200': (r) => r.status === 200 }, { step: 'login' })
  if (!ok) {
    throw new Error(`login failed: status ${res.status}`)
  }
  return res.json('access_token')
}

export default function () {
  const token = login()
  const title = `synthetic-${Date.now()}`
  const headers = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
    'X-Request-ID': requestId(),
    'X-Synthetic': 'true',
  }
  const created = http.post(`${baseUrl}/tasks`, JSON.stringify({ title }), {
    headers,
    tags: { step: 'create' },
  })
  const createdOk = check(
    created,
    {
      'create 201': (r) => r.status === 201,
      'create title': (r) => r.json('title') === title,
    },
    { step: 'create' },
  )
  if (!createdOk) {
    throw new Error(`create failed: status ${created.status}`)
  }
  const id = created.json('id')
  const read = http.get(http.url`${baseUrl}/tasks/${id}`, {
    headers: { ...headers, 'X-Request-ID': requestId() },
    tags: { step: 'read' },
  })
  const readOk = check(
    read,
    {
      'read 200': (r) => r.status === 200,
      'read id': (r) => r.json('id') === id,
      'read title': (r) => r.json('title') === title,
    },
    { step: 'read' },
  )
  if (!readOk) {
    throw new Error(`read failed: status ${read.status}`)
  }
  move(id, 'start', 'in_progress', headers)
  move(id, 'complete', 'completed', headers)
}

function move(id, action, status, headers) {
  const res = http.patch(http.url`${baseUrl}/tasks/${id}/${action}`, null, {
    headers: { ...headers, 'X-Request-ID': requestId() },
    tags: { step: action },
  })
  const ok = check(
    res,
    {
      [`${action} 200`]: (r) => r.status === 200,
      [`${action} status`]: (r) => r.json('status') === status,
    },
    { step: action },
  )
  if (!ok) {
    throw new Error(`${action} failed: status ${res.status}`)
  }
}
