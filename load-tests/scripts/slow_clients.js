/**
 * slow_clients.js — Long-held connections and slow consumer behaviour
 *
 * RUN
 *   k6 run load-tests/scripts/slow_clients.js
 */

import { check, group, sleep } from 'k6'
import { Counter, Gauge } from 'k6/metrics'
import { randomIntBetween, login, listTasks, getTask, reqTags } from '../lib/helpers.js'

// ─── Custom metrics ────────────────────────────────────────────────────────
const timeouts504 = new Counter('nginx_504_timeouts')
const slowBrowserReads = new Counter('slow_browser_requests')
const heavyReaderReads = new Counter('heavy_reader_requests')
const normalReaderOk = new Counter('normal_reader_ok')
const thinkTimeGauge = new Gauge('last_think_time_ms')

// ─── Test configuration ────────────────────────────────────────────────────
export const options = {
  scenarios: {
    normal_reader: {
      executor: 'constant-vus',
      vus: 10,
      duration: '3m',
      exec: 'normalReader',
      gracefulStop: '5s',
    },

    slow_browser: {
      executor: 'constant-vus',
      vus: 30,
      duration: '3m',
      exec: 'slowBrowser',
      startTime: '5s',
      gracefulStop: '5s',
    },

    heavy_reader: {
      executor: 'constant-vus',
      vus: 10,
      duration: '3m',
      exec: 'heavyReader',
      startTime: '10s',
      gracefulStop: '35s',
    },
  },

  thresholds: {
    normal_reader_ok: ['count>50'],
    http_req_failed: ['rate<0.15'],
    nginx_504_timeouts: ['count<100'],
    'http_req_duration{endpoint:get_tasks}': ['p(95)<10000'],
  },
}

// ─── One-time setup ────────────────────────────────────────────────────────
export function setup() {
  const token = login('admin', 'admin123', reqTags('slow_clients', 'login'))
  if (!token) throw new Error('Setup failed: could not obtain JWT')
  return { token }
}

export function normalReader(data) {
  group('normal_read', () => {
    const res = listTasks(data.token, reqTags('normal_reader', 'get_tasks'))

    const ok = check(res, {
      'normal: 200': r => r.status === 200,
      'normal: not gateway': r => r.status !== 502 && r.status !== 504,
    })

    if (ok) normalReaderOk.add(1)
  })

  const thinkMs = randomIntBetween(1000, 3000)
  thinkTimeGauge.add(thinkMs)
  sleep(thinkMs / 1000)
}

export function slowBrowser(data) {
  group('slow_browse', () => {
    const listRes = listTasks(data.token, reqTags('slow_browser', 'get_tasks'))
    check(listRes, { 'slow: list 200': r => r.status === 200 })
    slowBrowserReads.add(1)

    const thinkMs = randomIntBetween(8000, 20000)
    thinkTimeGauge.add(thinkMs)
    sleep(thinkMs / 1000)

    if (listRes.status === 200) {
      let tasks
      try {
        tasks = JSON.parse(listRes.body)
      } catch {
        tasks = []
      }

      if (tasks.length > 0) {
        const taskId = tasks[Math.floor(Math.random() * tasks.length)].id
        const getRes = getTask(
          data.token,
          taskId,
          reqTags('slow_browser', 'get_task'),
        )
        check(getRes, { 'slow: get task 200': r => r.status === 200 })
        slowBrowserReads.add(1)
      }
    }
  })

  sleep(randomIntBetween(2000, 5000) / 1000)
}

export function heavyReader(data) {
  group('heavy_read', () => {
    const listRes = listTasks(data.token, reqTags('heavy_reader', 'get_tasks'))
    heavyReaderReads.add(1)

    if (listRes.status === 504) {
      timeouts504.add(1)
    }

    check(listRes, {
      'heavy: got a response': r => r.status > 0,
      'heavy: not 502': r => r.status !== 502,
    })
  })

  const thinkMs = randomIntBetween(25000, 35000)
  thinkTimeGauge.add(thinkMs)
  sleep(thinkMs / 1000)
}
