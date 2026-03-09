docker compose \
    --profile core \
    --profile observability \
    --profile datadog \
    up --build

---

localhost:5173 - frontend React

localhost:3002 - frontend Next

localhost:8080 - Kafka UI

localhost:5540 - Redis

localhost:9090 - Prometheus

localhost:3001 - Grafana

localhost:5601 - Kibana

app.datadoghq.com - Datadog