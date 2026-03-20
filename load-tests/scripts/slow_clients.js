/**
 * slow_clients.js — Long-held connections and slow consumer behaviour
 *
 * PURPOSE
 *   Simulate clients that open connections and sit idle for long periods
 *   before issuing the next request.  This targets several failure modes:
 *
 *     1. CONNECTION POOL EXHAUSTION
 *        Many VUs holding idle keep-alive connections can saturate the
 *        upstream connection pool (api-gateway → task-service) even though
 *        per-request latency looks fine.
 *
 *     2. NGINX PROXY TIMEOUTS
 *        Nginx is configured with proxy_read_timeout 30s.  The "heavy reader"
 *        scenario issues a request and then does nothing for >30 s — Nginx
 *        should close the upstream connection and return 504.
 *
 *     3. POSTGRES IDLE CONNECTIONS
 *        Long-lived VUs correlate with long-lived SQLAlchemy sessions if the
 *        connection is not returned to the pool between requests.  Watch for
 *        idle connection count creeping up in pg_stat_activity.
 *
 *     4. GRACEFUL DEGRADATION
 *        Even under connection pressure the system should keep responding
 *        for short-lived requests.  The "normal_reader" scenario runs
 *        concurrently to verify this.
 *
 * THREE CONCURRENT USER TYPES
 *
 *   normal_reader   — Regular users: 10 VUs, 1–3 s think time.
 *                     Baseline to confirm healthy requests still succeed.
 *
 *   slow_browser    — Slow clients: 30 VUs, 8–20 s think time.
 *                     Holds HTTP keep-alive connections; many concurrent
 *                     idle connections on the server side.
 *
 *   heavy_reader    — Pathological: 10 VUs, 25–35 s think time between a
 *                     task list and a follow-up single-task read.  At 30+ s
 *                     Nginx's proxy_read_timeout may trigger a 504 on the
 *                     upstream side (task-service), visible in Nginx logs.
 *
 * RUN
 *   k6 run load-tests/scripts/slow_clients.js
 *
 * WATCH
 *   Nginx upstream errors  : docker logs nginx --follow
 *                            look for: upstream timed out, 504
 *   Open connections       : http://localhost:9090 Prometheus
 *                            query: nginx_connections_active  (if nginx-exporter)
 *                            or:    ss -tnp | grep 8000 | wc -l  (in api-gateway container)
 *   Postgres idle sessions : docker exec -it postgres psql -U admin saas \
 *                              -c "SELECT state, count(*) FROM pg_stat_activity GROUP BY state;"
 *   Trace waterfall        : http://localhost:16686 Jaeger
 *                            Long gap between span start and DB call = connection wait
 */

import http from 'k6/http'
import { check, group, sleep } from 'k6'
import { Counter, Gauge, Trend } from 'k6/metrics'
import {
  randomIntBetween, login, listTasks, getTask,
} from '../lib/helpers.js'

// ─── Custom metrics ────────────────────────────────────────────────────────
const timeouts504        = new Counter('nginx_504_timeouts')
const slowBrowserReads   = new Counter('slow_browser_requests')
const heavyReaderReads   = new Counter('heavy_reader_requests')
const normalReaderOk     = new Counter('normal_reader_ok')
const thinkTimeGauge     = new Gauge('last_think_time_ms')

// ─── Test configuration ────────────────────────────────────────────────────
export const options = {
  scenarios: {
    // Baseline: confirm normal requests still succeed under connection pressure
    normal_reader: {
      executor:    'constant-vus',
      vus:         10,
      duration:    '3m',
      exec:        'normalReader',
      gracefulStop: '5s',
    },

    // Slow browsers: many idle connections held open
    slow_browser: {
      executor:    'constant-vus',
      vus:         30,
      duration:    '3m',
      exec:        'slowBrowser',
      startTime:   '5s',    // let normal readers warm up first
      gracefulStop: '5s',
    },

    // Heavy readers: think times long enough to approach proxy_read_timeout (30s)
    heavy_reader: {
      executor:    'constant-vus',
      vus:         10,
      duration:    '3m',
      exec:        'heavyReader',
      startTime:   '10s',
      gracefulStop: '35s',  // allow in-flight 30 s sleeps to complete
    },
  },

  thresholds: {
    // Normal readers must stay healthy even while slow clients hold connections
    'normal_reader_ok':    ['count>50'],
    http_req_failed:       ['rate<0.15'],   // slow clients may hit timeouts → 504

    // 504s are expected from heavy_reader hitting proxy_read_timeout
    // but should stay bounded (only the heavy scenario should trigger them)
    'nginx_504_timeouts':  ['count<100'],
  },
}

// ─── One-time setup ────────────────────────────────────────────────────────
export function setup() {
  const token = login()
  if (!token) throw new Error('Setup failed: could not obtain JWT')
  return { token }
}

// ─── Scenario A: normal_reader ─────────────────────────────────────────────
// Regular users with 1–3 s think time. Verifies the system remains responsive
// despite the connection pressure created by the other scenarios.
export function normalReader(data) {
  group('normal_read', () => {
    const res = listTasks(data.token)

    const ok = check(res, {
      'normal: 200':         r => r.status === 200,
      'normal: not gateway': r => r.status !== 502 && r.status !== 504,
    })

    if (ok) normalReaderOk.add(1)
  })

  const thinkMs = randomIntBetween(1000, 3000)
  thinkTimeGauge.add(thinkMs)
  sleep(thinkMs / 1000)
}

// ─── Scenario B: slow_browser ─────────────────────────────────────────────
// Simulates browsers / mobile clients that take 8–20 s between page loads.
// Each VU holds a keep-alive TCP connection open during the think time.
// Collectively 30 VUs create significant connection pressure on Nginx and
// the api-gateway → task-service upstream pool.
export function slowBrowser(data) {
  group('slow_browse', () => {
    // First call: list all tasks
    const listRes = listTasks(data.token)
    check(listRes, { 'slow: list 200': r => r.status === 200 })
    slowBrowserReads.add(1)

    // Simulate the client "reading the page" for a long time before the next
    // interaction.  The TCP connection stays in TIME_WAIT / ESTABLISHED on the
    // server side during this sleep.
    const thinkMs = randomIntBetween(8000, 20000)
    thinkTimeGauge.add(thinkMs)
    sleep(thinkMs / 1000)

    // Second call in the same keep-alive connection
    if (listRes.status === 200) {
      let tasks
      try { tasks = JSON.parse(listRes.body) } catch { tasks = [] }

      if (tasks.length > 0) {
        const taskId = tasks[Math.floor(Math.random() * tasks.length)].id
        const getRes = getTask(data.token, taskId)
        check(getRes, { 'slow: get task 200': r => r.status === 200 })
        slowBrowserReads.add(1)
      }
    }
  })

  // Short pause between outer iterations so VUs don't pile up
  sleep(randomIntBetween(2000, 5000) / 1000)
}

// ─── Scenario C: heavy_reader ─────────────────────────────────────────────
// Pathological clients: very long think times (25–35 s) that approach or
// exceed Nginx's proxy_read_timeout (30 s).
//
// What to observe:
//   - During the 25–35 s sleep, the connection is idle on the server.
//   - Nginx may emit an "upstream timed out" warning in its error log.
//   - When the next request is issued after a 30+ s gap, Nginx may have
//     already closed the upstream keep-alive connection — the next request
//     will open a fresh connection.  This is NOT a 504 (the client->Nginx
//     connection is still live) but it IS extra upstream connection churn.
//
// To trigger an actual 504 from proxy_read_timeout:
//   - Introduce artificial latency on the upstream via Toxiproxy:
//       curl -X POST http://localhost:8474/proxies/api-gateway-upstream/toxics \
//         -H 'Content-Type:application/json' \
//         -d '{"name":"slow","type":"latency","attributes":{"latency":35000}}'
//   - After that, requests that take > 30 s will get a 504 from Nginx.
export function heavyReader(data) {
  group('heavy_read', () => {
    const listRes = listTasks(data.token)
    heavyReaderReads.add(1)

    if (listRes.status === 504) {
      timeouts504.add(1)
    }

    check(listRes, {
      'heavy: got a response':  r => r.status > 0,
      'heavy: not 502':         r => r.status !== 502,
    })
  })

  // The defining characteristic: very long think time approaching or
  // exceeding proxy_read_timeout of 30 s.
  const thinkMs = randomIntBetween(25000, 35000)
  thinkTimeGauge.add(thinkMs)
  sleep(thinkMs / 1000)
}
