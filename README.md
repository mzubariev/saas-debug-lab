# SaaS Debug Lab

This repository simulates a production-like SaaS microservices architecture.

### Project goals:

`docs/PROJECT_SPEC.md`

### Architecture is described in:

`docs/ARCHITECTURE.md`

### Service relationships:

`docs/SERVICE_MAP.md`

## Useful commands

`docker compose --profile core --profile observability --profile datadog up --build`

## Services URLs to use in a browser

`localhost:5173` - frontend React

`localhost:3000` - frontend Next

`localhost:8080` - Kafka UI

`localhost:9090` - Prometheus

`localhost:3001` - Grafana

`localhost:5601` - Kibana

`localhost:16686` - Jaeger tracing UI

`app.datadoghq.com` - Datadog