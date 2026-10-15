/**
 * baseline.js — Steady load for soak / long-run validation
 *
 * GET /tasks is not paginated. The scheduler deletes only completed tasks
 * older than 5 minutes, so a soak that leaves rows in `created` grows the
 * list without bound and the p95 becomes payload size. Every task created
 * in an iteration is started and completed in that same iteration, which
 * keeps the table flat once cleanup runs.
 *
 * Each VU logs in through getToken() and refreshes the JWT when under
 * 2 minutes remain (access token TTL is 30 minutes).
 *
 * RUN
 *   k6 run load-tests/scripts/baseline.js
 *   k6 run --duration 12h load-tests/scripts/baseline.js   # long-running soak
 *
 * See load-tests/README.md and Makefile targets (load-baseline).
 */
import { check, sleep } from 'k6'
import {
  login,
  getToken,
  createTask,
  startTask,
  completeTask,
  listTasks,
  reqTags,
} from '../lib/helpers.js'

const SCENARIO = 'baseline'

export const options = {
  vus: 20,
  duration: '1h',
  thresholds: {
    'http_req_duration{endpoint:create_task}': [
      { threshold: 'p(95)<3500', abortOnFail: true, delayAbortEval: '1m' },
    ],
    'http_req_duration{endpoint:get_tasks}': [
      { threshold: 'p(95)<4000', abortOnFail: true, delayAbortEval: '1m' },
    ],
    http_req_failed: [
      { threshold: 'rate<0.05', abortOnFail: true, delayAbortEval: '1m' },
    ],
    checks: ['rate>0.99'],
  },
}

export function setup() {
  const session = login('admin', 'admin123', reqTags(SCENARIO, 'login'))
  if (!session) throw new Error('Setup failed: could not obtain JWT')
}

export default function () {
  const token = getToken('admin', 'admin123', reqTags(SCENARIO, 'login'))
  const created = createTask(
    token,
    `task-${__VU}-${__ITER}`,
    reqTags(SCENARIO, 'create_task'),
  )

  if (check(created, { 'create: 201': r => r.status === 201 })) {
    const taskId = created.json('id')
    const started = startTask(token, taskId, reqTags(SCENARIO, 'start_task'))
    if (check(started, { 'start: 200': r => r.status === 200 })) {
      const completed = completeTask(token, taskId, reqTags(SCENARIO, 'complete_task'))
      check(completed, { 'complete: 200': r => r.status === 200 })
    }
  }

  sleep(1)

  const listed = listTasks(token, reqTags(SCENARIO, 'get_tasks'))
  check(listed, { 'list: 200': r => r.status === 200 })

  sleep(1)
}
