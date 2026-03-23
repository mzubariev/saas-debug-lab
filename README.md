# SaaS Debug Lab

## Overview

SaaS Debug Lab is a production-like microservices system designed to simulate real-world distributed system failures and practice incident investigation.

The platform models a simplified SaaS / FinTech backend with asynchronous processing, external integrations, and observability tooling.

The system is intentionally designed to:

- behave like a real production environment
- fail in realistic ways
- provide full visibility via logs, metrics, and tracing
- inject failures intentionally (Chaos Engineering)

---

## Objectives

The primary objective is to build practical debugging skills in distributed systems.

### Core capabilities:

- Investigate incidents across multiple services
- Analyze logs, metrics, and traces
- Debug Kafka-based event flows
- Identify bottlenecks and failure points
- Understand cascading failures
- Practice real-world escalation workflows

---

## System Architecture

The system follows a microservices architecture with synchronous and asynchronous communication.

### Core components:

- **API Gateway** — request routing, JWT validation
- **auth-service** — authentication, JWT issuance
- **task-service** — core business logic and state machine
- **integration-service** — Inbound webhook HTTP API; publishes to Kafka (`webhook_inbound`, `webhook_dispatch`)
- **webhook-dispatcher** — Kafka consumer; outbound webhook delivery, retries, DLQ
- **webhook-simulator** — test double for the external webhook boundary; controllable fail rate, delay, and status per request
- **workers** — notification-worker, analytics-worker (Kafka consumers)
- **Postgres** — primary relational data store
- **Redis** — caching layer (task-service + auth-service)
- **Kafka** — asynchronous event streaming

---

## Observability Stack

The system includes full observability to simulate real production debugging.

- **Logging** — structured logs with correlation IDs
- **Metrics** — Prometheus-based metrics
- **Tracing** — distributed tracing (Jaeger/OpenTelemetry)

---

## Failure Simulation Model

The system supports controlled failure injection to reproduce real incidents.

### Approach:

- Failures are implemented using failure primitives (low-level fault injections)
- Each real-world scenario is a combination of primitives
- Failures can be triggered manually or automatically

### Examples of failure types:

- service crashes
- network latency / packet loss
- database slow queries
- cache failures
- Kafka lag / message loss
- external API failures

---

## Debugging Scenarios

The system includes a large set of predefined debugging scenarios based on real SaaS incidents.

These scenarios simulate:

- infrastructure failures
- application bugs
- data inconsistencies
- integration issues
- load-related problems

Each scenario is designed to be:

- reproducible
- observable
- diagnosable using standard tools

---

## Chaos Layer (Planned)

A chaos layer will be implemented to automate failure injection.

### Features:

- trigger specific failure primitives
- combine multiple failures
- simulate cascading incidents
- random failure generator for training

This enables:

- realistic incident simulation
- hands-on debugging practice without knowing the root cause

---

## Learning Artifacts

The project includes structured documentation for learning and reference.

### Incident Playbooks

For each scenario:

- symptoms
- investigation steps
- root cause
- resolution

---

### Troubleshooting Guides

General debugging frameworks:

- high latency
- service unavailable
- data inconsistency
- event processing issues

---

## Target Roles

This lab is designed to simulate real responsibilities of:

- Product Support Engineer
- Technical Support Engineer
- Escalation Engineer
- Integration Engineer
- Platform Support Engineer

---

## Non-Goals

To keep the project focused:

- no full production hardening
- no complex business domain logic
- no UI-heavy features
- no premature optimization

The focus is debuggability, not product completeness.

---

## Key Design Principles

- Observability-first — everything must be traceable
- Failure-first design — system is built to break
- Reproducibility — incidents must be repeatable
- Realism over complexity — simulate real issues, not edge-case noise
- Modularity — failures and services are loosely coupled

