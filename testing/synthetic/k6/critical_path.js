import http from 'k6/http'
import { check, group } from 'k6'
import secrets from 'k6/secrets'

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

const baseUrl = "http://nginx"

function requestId() {
  const vu = typeof __VU !== 'undefined' ? __VU : 'setup'
  const iter = typeof __ITER !== 'undefined' ? __ITER : 0
  return `k6-${vu}-${iter}-${Date.now()}`
}

function logStep(step, status, taskId, rid) {
  console.log(`step=${step} status=${status} task_id=${taskId} request_id=${rid}`)
}

function bodyId(res) {
  try {
    const id = res.json('id')
    return id == null ? '' : String(id)
  } catch (e) {
    return ''
  }
}

function login(username, password) {
  const rid = requestId()
  const res = http.post(
    `${baseUrl}/auth/token`,
    { username, password },
    {
      headers: { 'X-Request-ID': rid },
      tags: { step: 'login' },
    },
  )
  logStep('login', res.status, '', rid)
  const ok = check(
    res,
    { 'login status is 200': (r) => r.status === 200 },
    { step: 'login' },
  )
  if (!ok) {
    throw new Error(`login failed: status ${res.status}`)
  }
  return res.json('access_token')
}

export default async function () {
  const username = await secrets.get('synthetic-user')
  const password = await secrets.get('synthetic-password')
  if (!username || !password) {
    throw new Error('secrets synthetic-user and synthetic-password are required')
  }
  const token = group('login', () => login(username, password))
  const title = `synthetic-${Date.now()}`
  const headers = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
    'X-Synthetic': 'true',
  }
  const id = group('create', () => {
    const rid = requestId()
    const created = http.post(`${baseUrl}/tasks`, JSON.stringify({ title }), {
      headers: { ...headers, 'X-Request-ID': rid },
      tags: { step: 'create' },
    })
    logStep('create', created.status, bodyId(created), rid)
    const createdOk = check(
      created,
      {
        'create status is 201': (r) => r.status === 201,
        'create title matches the request': (r) => r.json('title') === title,
      },
      { step: 'create' },
    )
    if (!createdOk) {
      throw new Error(`create failed: status ${created.status}`)
    }
    return created.json('id')
  })
  group('read', () => {
    const rid = requestId()
    const read = http.get(http.url`${baseUrl}/tasks/${id}`, {
      headers: { ...headers, 'X-Request-ID': rid },
      tags: { step: 'read' },
    })
    logStep('read', read.status, id, rid)
    const readOk = check(
      read,
      {
        'read status is 200': (r) => r.status === 200,
        'read id matches the created task': (r) => r.json('id') === id,
        'read title matches the request': (r) => r.json('title') === title,
      },
      { step: 'read' },
    )
    if (!readOk) {
      throw new Error(`read failed: status ${read.status}`)
    }
  })
  group('start', () => move(id, 'start', 'in_progress', headers))
  group('complete', () => move(id, 'complete', 'completed', headers))
}

function move(id, action, status, headers) {
  const rid = requestId()
  const res = http.patch(http.url`${baseUrl}/tasks/${id}/${action}`, null, {
    headers: { ...headers, 'X-Request-ID': rid },
    tags: { step: action },
  })
  logStep(action, res.status, id, rid)
  const ok = check(
    res,
    {
      [`${action} status is 200`]: (r) => r.status === 200,
      [`${action} task status is ${status}`]: (r) => r.json('status') === status,
    },
    { step: action },
  )
  if (!ok) {
    throw new Error(`${action} failed: status ${res.status}`)
  }
}
