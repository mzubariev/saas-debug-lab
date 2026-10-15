# 📟  ON-CALL RUNBOOK

1. [⚡ RAPID ACTIONS](#-rapid-actions)
2. [⚡ PHASE 0 — FIRST RESPONSE (0–60 сек)](#-phase-0--first-response-060-сек)
3. [🟥 РАЗДЕЛ 1 — ERRORS ↑ (5xx / 502 / 504)](#-раздел-1--errors--5xx--502--504)
4. [🟧 РАЗДЕЛ 2 — LATENCY ↑](#-раздел-2--latency-)
5. [🔥 РАЗДЕЛ 3 — RATE LIMIT (429)](#-раздел-3--rate-limit-429)
6. [🟨 РАЗДЕЛ 4 — KAFKA / QUEUE LAG ↑](#-раздел-4--kafka--queue-lag-)
7. [🟦 РАЗДЕЛ 5 — PARTIAL / FLAKY](#-раздел-5--partial--flaky)
8. [🟪 РАЗДЕЛ 6 — DATA ISSUES](#-раздел-6--data-issues)
9. [⚠️ РАЗДЕЛ 7 — OBSERVABILITY ПРОБЛЕМЫ](#-раздел-7--observability-проблемы)
10. [🔌 ПРИЛОЖЕНИЕ A — Работа с контейнерами](#-приложение-a--работа-с-контейнерами)
11. [🧠 ПРИЛОЖЕНИЕ B — Быстрые шорткаты](#-приложение-b--быстрые-шорткаты-в-голове)
12. [⏱️ ПРИЛОЖЕНИЕ C — Алгоритм в бою](#-приложение-c--алгоритм-в-бою)
13. [⚡ ЗОЛОТОЕ ПРАВИЛО](#-золотое-правило)

---

## ⚡ RAPID ACTIONS

```py
1) ALERT -> кратко: в чем конкретно проблема?
2) Acknowledge/react / start a timer
3) Открываю Grafana:
  - в каких именно метриках проблема и в каком именно слое/сервисе/эндпоинте?
  - нагрузка или поломка?
  - 1 user / 1 endpoint/service / 1 region/shard / all - infra outage?

Layers: 
Client → CDN (cache) → LB → API gateway (routing) → Service → Cache (Redis) → DB
                                                            → Events stream (Kafka) → External API
                                                                                    → Workers/background-jobs                              

App → bug, deadlock, memory leak, cache, messaging
Data → DB, migrations, locks, corruption
External → API, payment, DNS, cloud provider
Infra → CPU, memory, disk, network/DNS, Kubernetes
Edge/CDN/TSL

Симптом	                  Вероятная причина
latency ↑ + CPU ↑	  saturation
errors ↑ + latency норм	  bug / validation
RPS ↑ резко	          traffic spike / attack
RPS норм + errors ↑	  dependency

4) Set Severity and Blast-radius / communicate
  - Auto/create: warroom, Zoom room, notify/invite all, set the Incident status
5) Проверяю в CLI kubectl -> FF enabled / deploy / config change?
  - Fastest Mitigation: FF disable OR rollback OR change config
6) Dig deeper per service
  - Grafana-Jaeger -> traces with latencies
  - kubectl get pods/node/events, describe pod, top pods, htop, uptime, mtr, memory_pressure
  - curl -v service/api:port/health || ping service/api:port
  - CLI -> pod/service/app logs, edge/Nginx logs
  - CLI psql / CLI kafka / CLI Redis / CLI Celery
  - iostat 1, dig, openssl, ps aux
7) Mitigations:
  - FF disable / rollback / change config
  - restart pod/service (memory leak)
  - scale horizontally pod/service (!когда система НЕ сломана, а просто не хватает ресурсов при большой нагрузке)
  - scale vertically (ex.: Redis memory +)
  - block DDoS IP / enable throttling->queue / set rate-limit (IP/region/endpoint)
  - Rollback db migration / kill db query / add index / REINDEX? / VACUUM? / kill idle connections / failover / add replicas
  - redis-cli FLUSH some part / evict cache
  - increase/decrease timeouts & retries in config via CLI
  - enable fallbacks / disable some heavy non-critical endpoints
  - bypass CDN
8) Root-Cause-Analysis (deeper investigation with diff-deploy/logs/tracing/profiling/API-checks)
9) !Recovery/Catch-up/Backfill/Reprocess! & Permanent fix
  - Fix a bug in a code/config
  - Improve/fix db query / add indexes / add db replicas / split read/write dbs
  - Introduce: exponential backoff - retries with jitter, fallback to cache/stub, curcuit breaker, cache warm-up / combine same requests / one request per time to fill out the cache, Kafka backpressure consumer->producer
  - Improve caching strategy/TTL, db VACUUM strategy, db tables REINDEXing strategy, Garbage-Collector strategy
  - Fix DNS, TSL/SSL certificates
  - Fix failing liveleness/readiness k8s probes (timeouts) -> add startup (early restarts prevention)
10) Post-Mortem doc
11) Permanent Improvements -> to prevent such issues or figure out in advance

```

---

## ⚡ PHASE 0 — FIRST RESPONSE (0–60 сек)

### 0.1 Acknowledge & Severity

Как только получил алерт — **acknowledge** его в системе (PagerDuty / OpsGenie / etc.) и **запусти таймер**.


| Severity | Описание                                        | SLA реакции |
| -------- | ----------------------------------------------- | ----------- |
| **P0**   | Полный outage, все пользователи не работают     | Немедленно  |
| **P1**   | Критичная деградация, большинство пользователей | < 5 мин     |
| **P2**   | Частичная деградация, часть пользователей       | < 15 мин    |
| **P3**   | Минорная проблема, workaround есть              | < 1 час     |


### 0.2 Первый вопрос: был ли недавний деплой?

```
Был деплой/enabled FF?  →  ДА  →  виновник — деплой (пока не доказано обратное)
                         → disable feature flag OR ROLLBACK первым делом
             →  НЕТ →  идём дальше по дереву

```

### 0.3 Определи характер изменения

```
Резко (spike)  →  feature flag / deploy / config change / crash / kill-сигнал / restart
Постепенно     →  load growth / memory leak / backlog накопление / disk full

```

### 0.4 Blast Radius — где проблема?

Пройди вопросы за 60 секунд:

1. **Все пользователи или часть?**
  - 1 user → вероятно data / edge case
  - subset → shard / region / feature / service / endpoint
  - all users → infra (сеть, DNS, LB, сторонний провайдер) / upstream / core dependency
2. **Регион-специфично?**
  - Да → смотри DNS, CDN, regional routing, AZ failover

### 0.5 Communication

- “Incident started”
- “Mitigation in progress”
- “Root cause under investigation”

### 0.6 Определи доминирующий сигнал (выбери ветку)

```
5xx ↑                  →  🟥 ERRORS   (раздел 1)
502 / 504 ↑            →  🟥 ERRORS → A1
p95 / p99 ↑            →  🟧 LATENCY  (раздел 2)
429 ↑ RPS ↑            →  🔥 RATE LIMIT (раздел 3)
Kafka / queue lag ↑    →  🟨 LAG      (раздел 4)
Partial / flaky        →  🟦 FLAKY    (раздел 5)
Данные пропали/дубли   →  🟪 DATA     (раздел 6)
Метрики не сходятся    →  ⚠️  OBSERVABILITY (раздел 7)

```

---

## 🟥 РАЗДЕЛ 1 — ERRORS ↑ (5xx / 502 / 504)

### Диагностика

```bash
# Посмотреть состояние подов
kubectl get pods -n <namespace>
kubectl get pods -n <namespace> -o wide  # с нодами

# Логи конкретного пода
kubectl logs <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace> --previous  # если под рестартовал

# Логи нескольких реплик сразу (по label)
kubectl logs -l app=<service-name> -n <namespace> --tail=100

# Health check напрямую
kubectl exec -it <pod-name> -n <namespace> -- curl -s http://localhost:<port>/health

# Или снаружи через port-forward
kubectl port-forward pod/<pod-name> 8080:<port> -n <namespace>
curl http://localhost:8080/health

```

### Быстрая классификация ошибки


| Код                       | Что означает                  | Первый шаг                                           |
| ------------------------- | ----------------------------- | ---------------------------------------------------- |
| **502 Bad Gateway**       | Downstream сервис не отвечает | Проверь downstream pods / health (`kubectl`, `curl`) |
| **504 Gateway Timeout**   | Downstream отвечает медленно  | Увеличь timeout, смотри latency                      |
| **500 Internal Error**    | Логика / код / payload        | Смотри stacktrace в логах                            |
| **429 Too Many Requests** | Rate limit                    | Раздел 3                                             |


---

### A1 — 502 / 504: Downstream недоступен

**Симптом:** Gateway возвращает 502/504, upstream сервис жив.

```bash
# Проверь downstream сервис
kubectl get pods -l app=<downstream-service> -n <namespace>
kubectl describe pod <pod-name> -n <namespace>  # OOMKilled? CrashLoopBackOff?

# Health endpoint downstream
kubectl exec -it <any-pod> -- curl -v http://<downstream-service>:<port>/health

# Проверь endpoints сервиса (есть ли живые поды за LB)
kubectl get endpoints <service-name> -n <namespace>

# Events по сервису
kubectl get events -n <namespace> --sort-by='.lastTimestamp' | tail -20

```

**Митигейшн:**

```bash
# 1. Рестарт downstream сервиса
kubectl rollout restart deployment/<downstream-service> -n <namespace>

# 2. Если был деплой — откат
kubectl rollout undo deployment/<downstream-service> -n <namespace>
kubectl rollout status deployment/<downstream-service> -n <namespace>  # следи за прогрессом

# 3. Увеличь timeout (в configmap / env)
kubectl edit deployment/<service-name> -n <namespace>
# или
kubectl set env deployment/<service-name> DOWNSTREAM_TIMEOUT=5s -n <namespace>

# 4. Включи fallback (feature flag / env)
kubectl set env deployment/<service-name> ENABLE_EXTERNAL_API=false -n <namespace>
```

**Перманентный фикс:**

- Добавить circuit breaker (Hystrix, Resilience4j, или library уровня)
- Настроить retry с exponential backoff
- Health check в Kubernetes readinessProbe
- Задокументировать graceful degradation

---

### A2 — 500: Ошибка логики / payload / контракт

**Симптом:** 500 errors, latency норм, downstream живой.

```bash
# Найди stacktrace
kubectl logs <pod> -n <namespace> | grep -A 20 "ERROR\|Exception\|panic"

# Фильтр по времени начала инцидента
kubectl logs <pod> -n <namespace> --since=10m | grep -i error

# Посмотри последние деплои
kubectl rollout history deployment/<service-name> -n <namespace>

# Что изменилось в последнем деплое
kubectl describe deployment/<service-name> -n <namespace>
```

**Митигейшн:**

```bash
# Откат если был деплой
kubectl rollout undo deployment/<service-name> -n <namespace>

# Если проблема в конфиге
kubectl get configmap <name> -n <namespace> -o yaml
kubectl edit configmap <name> -n <namespace>
# После изменения configmap — рестарт (автоматически не применяется)
kubectl rollout restart deployment/<service-name> -n <namespace>

```

**Перманентный фикс:**

- Input validation на уровне API
- Contract testing (Pact)
- Canary deployments для раннего обнаружения

---

### A3 — Cascading Failure (Errors + Latency ↑)

**Симптом:** Ошибки растут, latency тоже, зависимость деградирует.

**Митигейшн (в этом порядке):**

```bash
# 1. Включи circuit breaker / fallback
kubectl set env deployment/<service-name> CIRCUIT_BREAKER_ENABLED=true -n <namespace>

# 2. Rate limit на gateway (nginx/envoy/traefik)
# Пример для nginx ingress:
kubectl annotate ingress <ingress-name> -n <namespace> \
  nginx.ingress.kubernetes.io/limit-rps="50"

# 3. Отключи нагрузку на зависимость
kubectl set env deployment/<service-name> ENABLE_HEAVY_FEATURE=false -n <namespace>

# 4. Scale dependency
kubectl scale deployment/<dependency> --replicas=10 -n <namespace>
```

**Перманентный фикс:**

- Circuit breaker pattern для всех внешних зависимостей
- Bulkhead pattern — изоляция пулов потоков
- Определить SLO для каждой зависимости

---

## 🟧 РАЗДЕЛ 2 — LATENCY ↑

### Диагностика

```bash
# CPU и память
kubectl top pods -n <namespace>
kubectl top pods -n <namespace> --sort-by=cpu

# Описание пода (лимиты, requests)
kubectl describe pod <pod-name> -n <namespace> | grep -A 10 "Limits\|Requests"

# Логи медленных запросов
kubectl logs <pod-name> -n <namespace> | grep -i "slow\|timeout\|duration" | tail -50

# Посмотри на трейсы (если Jaeger/Zipkin/Tempo — открой UI)
# Найди longest span — он укажет на bottleneck

```

### Дерево диагностики latency

```
CPU ↑ → CPU-bound (раздел 2.1)
CPU норм → I/O-bound (раздел 2.2)
  ├── Kafka lag? → Consumer bottleneck (раздел 3)
  ├── p95 ↑ но p50 норм → Tail latency (раздел 2.3)
  └── Cache hit rate ↓ → Cache stampede (раздел 2.4)

```

---

### 2.1 — CPU-Bound

**Симптом:** `kubectl top pods` показывает высокий CPU у pod.

```bash
# Подключись к поду для профилирования
kubectl exec -it <pod-name> -n <namespace> -- bash

# Внутри пода:
top -H  # потоки
# Для Java:
jstack <pid>      # thread dump
jmap -histo <pid> # heap histogram
# Для Go:
kill -SIGPROF <pid>  # pprof trigger
# Для Node.js — нужен --prof флаг заранее
```

**Митигейшн:**

```bash
# Scale horizontally
kubectl scale deployment/<service-name> --replicas=5 -n <namespace>

# Если был деплой (новый тяжелый код) — откат
kubectl rollout undo deployment/<service-name> -n <namespace>

# Увеличь CPU limits временно
kubectl edit deployment/<service-name> -n <namespace>
# В spec.containers[].resources.limits.cpu: "2000m"

```

**Перманентный фикс:**

- Оптимизация горячих путей кода
- Кэширование результатов тяжелых вычислений
- HPA (Horizontal Pod Autoscaler) с правильными threshold

---

### 2.2 — I/O Bound (DB / Network / External API)

**Симптом:** CPU норм, latency высокая → смотри I/O.

```bash
# Медленные запросы в PostgreSQL
kubectl exec -it <postgres-pod> -n <namespace> -- psql -U <user> -d <db>

-- Найти медленные запросы
SELECT query, 
       calls,
       round(mean_exec_time::numeric, 2) AS mean_ms,
       round(total_exec_time::numeric, 2) AS total_ms
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Активные долгие запросы прямо сейчас
SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
FROM pg_stat_activity
WHERE state != 'idle' 
  AND (now() - pg_stat_activity.query_start) > interval '5 seconds';

-- Убить зависший запрос
SELECT pg_cancel_backend(<pid>);   -- мягко
SELECT pg_terminate_backend(<pid>); -- жёстко

-- Индексы (нет ли seq scan на большой таблице?)
EXPLAIN ANALYZE <slow_query>;
```

```bash
# Проверь сеть до external API
kubectl exec -it <pod-name> -n <namespace> -- curl -o /dev/null -s -w "%{time_total}" https://api.external.com/health
kubectl exec -it <pod-name> -n <namespace> -- ping -c 5 api.external.com
```

**Митигейшн:**

```bash
# 1. Включи/усиль кэш
kubectl set env deployment/<service-name> CACHE_TTL=300 CACHE_ENABLED=true -n <namespace>
kubectl rollout restart deployment/<service-name> -n <namespace>

# 2. Scale DB read replicas (если настроено)
kubectl scale deployment/postgres-replica --replicas=3 -n <namespace>

# 3. Убей тяжелые запросы (если нашёл через pg_stat_activity)
# (команды выше в psql)

# 4. Rate limit тяжелых endpoints
kubectl annotate ingress <ingress-name> -n <namespace> \
  nginx.ingress.kubernetes.io/limit-rps="20"

```

**Перманентный фикс:**

- Добавить индексы на медленные запросы
- Connection pooling (PgBouncer)
- Read/Write split
- Query optimization

---

### 2.3 — Tail Latency (p95 ↑, p50 норм)

**Симптом:** Медиана нормальная, но хвост (95/99) высокий.

**Причины:** GC паузы, lock contention, jitter, hot spots.

```bash
# GC логи (JVM)
kubectl logs <pod-name> | grep -i "GC\|pause\|safepoint"

# Tail requests в access log
kubectl logs <pod-name> | awk '$NF > 1000'  # запросы > 1сек (зависит от формата)

# Lock contention (PostgreSQL)
SELECT * FROM pg_locks WHERE NOT granted;

```

**Митигейшн:**

- Tune GC (heap size, GC algorithm)
- Добавить jitter в retry логику
- Уменьшить contention: шардирование, оптимистичные локи

---

### 2.4 — Cache Stampede

**Симптом:** Cache hit rate упал, latency резко выросла, DB под нагрузкой.

```bash
# Redis — статистика
kubectl exec -it <redis-pod> -n <namespace> -- redis-cli INFO stats | grep -E "hits|misses|keyspace"
kubectl exec -it <redis-pod> -n <namespace> -- redis-cli INFO memory

# Конкретный ключ
kubectl exec -it <redis-pod> -n <namespace> -- redis-cli GET "task:123"
kubectl exec -it <redis-pod> -n <namespace> -- redis-cli TTL "task:123"
```

**Митигейшн:**

```bash
# 1. Прогрев кэша (если есть скрипт)
kubectl exec -it <service-pod> -n <namespace> -- ./scripts/warm-cache.sh

# 2. Rate limit запросов к DB пока кэш не прогреется
kubectl set env deployment/<service-name> DB_RATE_LIMIT=100 -n <namespace>

# 3. Scale DB
kubectl scale deployment/postgres --replicas=3 -n <namespace>
```

**Перманентный фикс:**

- Staggered TTL (randomize)
- Cache warming при деплое
- Probabilistic early expiration (PER)

---

## 🔥 РАЗДЕЛ 3 — RATE LIMIT (429)

### Диагностика

```bash
# Найди 429 в логах
kubectl logs <pod-name> -n <namespace> | grep "429\|rate.limit\|too many" | tail -50

# Откуда идут запросы (если есть access log)
kubectl logs <ingress-pod> -n ingress-nginx | grep "429" | awk '{print $1}' | sort | uniq -c | sort -rn

# Метрики retry
# В Prometheus: rate(http_requests_total{status="429"}[5m])

```

### Митигейшн

```bash
# 1. Снизить RPS на gateway
kubectl annotate ingress <ingress-name> -n <namespace> \
  nginx.ingress.kubernetes.io/limit-rps="50" \
  nginx.ingress.kubernetes.io/limit-connections="10"

# 2. Снизить retry на клиентах
kubectl set env deployment/<client-service> RETRY_COUNT=2 -n <namespace>

# 3. Добавить кэш (если запросы повторяются)
kubectl set env deployment/<service-name> CACHE_ENABLED=true CACHE_TTL=60 -n <namespace>

# 4. Временно увеличить rate limit на upstream (если это твой сервис)
kubectl set env deployment/<service-name> RATE_LIMIT_RPS=1000 -n <namespace>

```

**Перманентный фикс:**

- Token bucket / leaky bucket алгоритм
- Экспоненциальный backoff на клиентах
- Кэширование идемпотентных запросов
- Квоты per-client

---

## 🟨 РАЗДЕЛ 4 — KAFKA / QUEUE LAG ↑

### Диагностика

```bash
# Lag по consumer group
kubectl exec -it <kafka-pod> -n <namespace> -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group <consumer-group>

# Все consumer groups
kubectl exec -it <kafka-pod> -n <namespace> -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list

# Логи consumer
kubectl logs -l app=<consumer-service> -n <namespace> --tail=100

# Состояние consumer подов
kubectl get pods -l app=<consumer-service> -n <namespace>

```

### Дерево диагностики lag

```
Есть ошибки в consumer? 
  ДА →  Consumer сломан: crash / parsing error / retry loop
        → Смотри stacktrace, исправь или откатись

  НЕТ → Consumer работает, но медленный / завис
        → Traffic spike? 
            ДА → Scale consumers
            НЕТ → Consumer завис, рестарт

```

### Митигейшн

```bash
# 1. Рестарт consumer
kubectl rollout restart deployment/<consumer-service> -n <namespace>

# 2. Scale consumers (в рамках партиций топика)
kubectl scale deployment/<consumer-service> --replicas=5 -n <namespace>
# ⚠️ Реплик не может быть больше, чем партиций в топике

# 3. Если consumer в crash loop — откат
kubectl rollout undo deployment/<consumer-service> -n <namespace>

# 4. Снизить нагрузку со стороны producer
kubectl set env deployment/<producer-service> PRODUCER_RATE_LIMIT=500 -n <namespace>

# 5. Если poison pill message — пропустить оффсет (осторожно!)
kubectl exec -it <kafka-pod> -n <namespace> -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group <group> --topic <topic> --reset-offsets --to-offset <N+1> --execute

```

**Перманентный фикс:**

- Dead Letter Queue (DLQ) для poison pills
- Backpressure механизм на producer
- Monitoring lag с alerting на threshold
- Consumer timeout и heartbeat настройка

---

## 🟦 РАЗДЕЛ 5 — PARTIAL / FLAKY

### Диагностика

```bash
# Проверь: один и тот же запрос иногда OK, иногда FAIL?
for i in {1..10}; do
  curl -o /dev/null -s -w "Status: %{http_code}\n" http://<service>/health
  sleep 0.5
done

# Сетевые проблемы
kubectl exec -it <pod-name> -n <namespace> -- ping -c 10 <target-host>
kubectl exec -it <pod-name> -n <namespace> -- traceroute <target-host>

# Packet loss
kubectl exec -it <pod-name> -n <namespace> -- mtr -rwzbc100 <target-host>

# Retry spikes в метриках / логах
kubectl logs <pod-name> | grep -i "retry\|retrying" | tail -50

# Посмотри на конкретный pod (может проблема только в одном)
kubectl get pods -n <namespace> -o wide
# Если есть плохой под — посмотри его логи отдельно

```

### Быстрое правило

```
Иногда работает, иногда нет → это НЕ код → сеть / нестабильная зависимость / shard

```

### Митигейшн

```bash
# 1. Включи retry с backoff
kubectl set env deployment/<service-name> \
  RETRY_COUNT=5 \
  RETRY_BACKOFF=exponential \
  RETRY_MAX_DELAY=10s \
  -n <namespace>

# 2. Увеличь timeout
kubectl set env deployment/<service-name> REQUEST_TIMEOUT=5s -n <namespace>

# 3. Включи fallback
kubectl set env deployment/<service-name> FALLBACK_ENABLED=true -n <namespace>

# 4. Если конкретный под нестабилен — убей его (k8s поднимет новый)
kubectl delete pod <bad-pod-name> -n <namespace>

```

**Перманентный фикс:**

- Retry policy с jitter
- Circuit breaker
- Health checks + readiness/liveness probes
- Анализ network policies

---

## 🟪 РАЗДЕЛ 6 — DATA ISSUES

### Диагностика

```bash
# Проверь: данные в DB vs API
# В PostgreSQL:
kubectl exec -it <postgres-pod> -n <namespace> -- psql -U <user> -d <db> \
  -c "SELECT * FROM tasks WHERE id = <X>;"

# Через API
kubectl exec -it <any-pod> -- curl http://<service>/tasks/<X>

# Redis
kubectl exec -it <redis-pod> -n <namespace> -- redis-cli GET "task:<X>"
kubectl exec -it <redis-pod> -n <namespace> -- redis-cli TTL "task:<X>"

# Kafka: нет ли застрявших сообщений
kubectl exec -it <kafka-pod> -n <namespace> -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group <group>
```

### Классификация data issues


| Симптом              | Причина                                     | Действие                               |
| -------------------- | ------------------------------------------- | -------------------------------------- |
| Данные не появляются | Kafka / consumer завис                      | Раздел 4                               |
| Дубликаты            | Retry без idempotency                       | Включить dedup / idempotency key       |
| DB ≠ API             | Cache устарел / race condition              | Очистить кэш                           |
| Частичные данные     | Partial failure / транзакция не завершилась | Проверь транзакции, включи idempotency |


### Митигейшн

```bash
# 1. Остановить запись (если критично — данные повреждаются)
kubectl set env deployment/<service-name> WRITE_ENDPOINT_ENABLED=false -n <namespace>
# или через feature flag

# 2. Очистить кэш (ОСТОРОЖНО — stampede риск)
kubectl exec -it <redis-pod> -n <namespace> -- redis-cli FLUSHDB
# Лучше — удалить конкретные ключи
kubectl exec -it <redis-pod> -n <namespace> -- redis-cli DEL "task:<X>"
kubectl exec -it <redis-pod> -n <namespace> -- redis-cli KEYS "task:*" | xargs redis-cli DEL

# 3. Включить idempotency / deduplication
kubectl set env deployment/<service-name> IDEMPOTENCY_ENABLED=true -n <namespace>

```

**Перманентный фикс:**

- Idempotency keys для всех write операций
- Exactly-once semantics в Kafka
- Outbox pattern для distributed writes
- Cache invalidation strategy

---

## ⚠️ РАЗДЕЛ 7 — OBSERVABILITY ПРОБЛЕМЫ

### Признак

```
Метрики говорят одно, логи — другое, пользователи жалуются на третье.

```

### Действия

```bash
# 1. ИГНОРИРУЙ метрики — они могут быть сломаны

# 2. Проверяй напрямую
kubectl logs <pod-name> -n <namespace> --tail=200
kubectl exec -it <pod-name> -- curl -s http://localhost:<port>/health

# 3. Проверяй DB напрямую
kubectl exec -it <postgres-pod> -n <namespace> -- psql -U <user> -d <db> \
  -c "SELECT count(*) FROM requests WHERE created_at > now() - interval '5 minutes';"

# 4. Проверяй реальные ответы сервиса
kubectl port-forward pod/<pod-name> 8080:<port> -n <namespace>
curl -v http://localhost:8080/api/endpoint

# 5. Проверь, не упал ли сам сбор метрик
kubectl get pods -n monitoring
kubectl logs -l app=prometheus -n monitoring --tail=50
```

**Перманентный фикс:**

- Алертить на health самого observability стека
- Synthetic monitoring (внешние проверки)
- Сопоставление метрик с бизнес-метриками

---

## 🔌 ПРИЛОЖЕНИЕ A — Работа с контейнерами

### Docker — частые команды (если без k8s)

```bash
# Список контейнеров
docker ps
docker ps -a  # включая остановленные

# Войти в контейнер
docker exec -it <container-id-or-name> bash
docker exec -it <container-id-or-name> sh  # если bash нет

# Логи
docker logs <container-name>
docker logs <container-name> --tail=100 -f  # follow

# Рестарт
docker restart <container-name>

# Статистика ресурсов
docker stats <container-name>

# Инспект (конфиг, сети, volumes)
docker inspect <container-name>

# Переменные окружения в контейнере
docker exec <container-name> env

# Compose (лаборатория: из каталога infra, профиль core или observability)
cd infra
docker compose --profile core pull <service>
docker compose --profile core up -d <service>

```

### Kubernetes — частые команды

```bash
# Все поды в namespace
kubectl get pods -n <namespace> -o wide

# Поды всех namespaces
kubectl get pods -A

# Войти в контейнер (bash)
kubectl exec -it <pod-name> -n <namespace> -- bash
# Если bash нет:
kubectl exec -it <pod-name> -n <namespace> -- sh

# Войти в конкретный контейнер в multi-container поде
kubectl exec -it <pod-name> -n <namespace> -c <container-name> -- bash

# Логи с фильтром
kubectl logs <pod> -n <namespace> --since=15m
kubectl logs <pod> -n <namespace> -f  # follow (tail -f)
kubectl logs <pod> -n <namespace> --previous  # предыдущий (если рестартовал)

# Port-forward (локальный доступ к поду)
kubectl port-forward pod/<pod-name> 8080:8080 -n <namespace>
kubectl port-forward svc/<service-name> 8080:80 -n <namespace>

# Описание пода (события, статус)
kubectl describe pod <pod-name> -n <namespace>

# Масштабирование
kubectl scale deployment/<name> --replicas=5 -n <namespace>

# Роллаут
kubectl rollout status deployment/<name> -n <namespace>
kubectl rollout history deployment/<name> -n <namespace>
kubectl rollout undo deployment/<name> -n <namespace>
kubectl rollout undo deployment/<name> --to-revision=2 -n <namespace>

# Переменные окружения
kubectl set env deployment/<name> KEY=value -n <namespace>
kubectl exec -it <pod> -- env | grep KEY  # проверить

# ConfigMap
kubectl get configmap <name> -n <namespace> -o yaml
kubectl edit configmap <name> -n <namespace>

# Secrets
kubectl get secret <name> -n <namespace> -o jsonpath='{.data.<key>}' | base64 -d

# Ресурсы
kubectl top pods -n <namespace>
kubectl top nodes

# Events (хронологически)
kubectl get events -n <namespace> --sort-by='.lastTimestamp' | tail -30

```

---

## 🧠 ПРИЛОЖЕНИЕ B — Быстрые шорткаты (в голове)

```
Резко сломалось       →  деплой / FF enabled → disable FF / rollback
Постепенно            →  load / leak / backlog → scale / restart / profile
502 / 504             →  downstream → check containers, restart
500 + latency норм    →  код / логика → смотри stacktrace
p95 ↑ CPU норм        →  DB или сеть → pg_stat_statements, tracing
CPU ↑                 →  heavy code, Infinitive loop, spike, load → scale, rate limit, profiling
lag ↑                 →  consumer → restart, scale
retry ↑               →  нестабильная зависимость → fallback, backoff, throttling on edge (Nginx)
частично              →  сеть / shard → mtr, ping, curl loop
429                   →  rate limit → снизь retry, добавь кэш, throttling on edge (Nginx)
дубликаты             →  retry без idempotency → dedup
нет логов             →  observability сломан → curl напрямую, DB

```

---

## 🧭 ПРИЛОЖЕНИЕ C — Алгоритм в бою

```
[ALERT пришёл]
     │
     ▼
0. Acknowledge + запустить таймер + определить severity
     │
     ▼
1. Был деплой/FF enabled? → ДА → FF disable/ROLLBACK немедленно, потом смотри
     │
     ▼
2. Blast radius: все / сервис / endpoint?
     │
     ▼
3. Доминирующий сигнал → выбрать раздел (1–7)
     │
     ▼
4. Быстрая диагностика (2–3 ключевых команды)
     │
     ▼
5. MITIGATION → стабилизировать систему
     │
     ▼
6. Подтвердить: метрики улучшаются? errors ↓ latency ↓
     │
     ▼
7. ТОЛЬКО ПОСЛЕ стабилизации → глубокий RCA
     │
     ▼
8. Перманентный фикс (раздел в документе выше)
     │
     ▼
9. Postmortem / документация

```

---

## ⚡ ЗОЛОТОЕ ПРАВИЛО

```
СНАЧАЛА:   Стабилизируй систему. Любым способом.
ПОТОМ:     Ищи root cause.
НИКОГДА:   Не делай рискованные изменения под нагрузкой без rollback плана.

```

---

