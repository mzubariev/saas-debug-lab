# System Architecture

SaaS Debug Lab simulates a production-like distributed backend architecture.

The system is built using a microservices architecture with both synchronous and asynchronous communication.

Main components:

API Gateway
FastAPI-based gateway responsible for routing external requests to internal services.

Services

auth-service
Handles authentication and user identity.

task-service
Core business logic service responsible for task creation and management.

Workers

notification-worker
Consumes Kafka events and sends notifications (uses Celery + Flower).

analytics-worker
Processes event streams and aggregates analytics data (uses Celery + Flower).

Infrastructure

Postgres
Primary relational database.

Redis
Used for caching and temporary data storage.

Kafka
Event streaming platform used for asynchronous communication between services.

Communication

REST
Used for synchronous service-to-service communication.

Kafka Events
Used for asynchronous event-driven workflows.

Frontends

React Dashboard
Operational dashboard for viewing tasks and system state.

NextJS Dashboard
Admin interface.

Observability

ELK Stack
Centralized logging.

Prometheus
Metrics collection.

Grafana
Metrics dashboards.

OpenTelemetry
Distributed tracing instrumentation.

Jaeger
Tracing visualization.

Datadog
External observability platform.