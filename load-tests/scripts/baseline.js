/**
 * baseline.js — Steady load for soak / long-run validation
 *
 * RUN
 *   k6 run load-tests/scripts/baseline.js
 *   k6 run --duration 12h load-tests/scripts/baseline.js   # long-running soak
 *
 * See load-tests/README.md and Makefile targets (load-baseline).
 */
import { sleep } from 'k6'
import { login, createTask, listTasks, reqTags } from '../lib/helpers.js'

const SCENARIO = 'baseline'

export const options = {
  vus: 20,
  duration: '1h',
  thresholds: {
    'http_req_duration{endpoint:create_task}': ['p(95)<800'],
    'http_req_duration{endpoint:get_tasks}': ['p(95)<500'],
    http_req_failed: ['rate<0.05'],
  },
}

export function setup() {
  const token = login('admin', 'admin123', reqTags(SCENARIO, 'login'))
  if (!token) throw new Error('Setup failed: could not obtain JWT')
  return { token }
}

export default function (data) {
  createTask(data.token, `task-${__VU}-${__ITER}`, reqTags(SCENARIO, 'create_task'))

  sleep(1)

  listTasks(data.token, reqTags(SCENARIO, 'get_tasks'))

  sleep(1)
}
