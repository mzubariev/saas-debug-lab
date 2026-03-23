/**
 * chaos_mode.js — Unstable client behaviour
 *
 * - create task; if status != 201 → retry once
 * - random sleep 0–2s between iterations
 * - tags: scenario=chaos_mode
 *
 * RUN
 *   k6 run load-tests/scripts/chaos_mode.js
 *   make load-chaos
 */
import { sleep } from 'k6'
import { check } from 'k6'
import {
  login,
  createTask,
  reqTags,
  randomIntBetween,
} from '../lib/helpers.js'

const SCENARIO = 'chaos_mode'

export const options = {
  vus: 10,
  duration: '5m',
  thresholds: {
    'http_req_duration{endpoint:create_task}': ['p(95)<1200'],
    http_req_failed: ['rate<0.15'],
  },
}

export function setup() {
  const token = login('admin', 'admin123', reqTags(SCENARIO, 'login'))
  if (!token) throw new Error('Setup failed: could not obtain JWT')
  return { token }
}

export default function (data) {
  if (__ENV.DEBUG_VU === '1') {
    console.log(`VU=${__VU} ITER=${__ITER}`)
  }

  const tags = reqTags(SCENARIO, 'create_task')
  let res = createTask(data.token, `chaos-${__VU}-${__ITER}`, tags)

  if (res.status !== 201) {
    sleep(randomIntBetween(0, 2000) / 1000)
    res = createTask(data.token, `chaos-retry-${__VU}-${__ITER}`, tags)
  }

  check(res, {
    'create eventually 201': r => r.status === 201,
  })

  sleep(randomIntBetween(0, 2000) / 1000)
}
