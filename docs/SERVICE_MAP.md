# Service Map

External request flow:

Client
  ↓
Nginx
  ↓
API Gateway
  ↓
task-service
  ↓
Postgres

Event flow:

task-service
  ↓
Kafka event: task_created
  ↓
notification-worker
  ↓
send notification

Analytics flow:

task-service
  ↓
Kafka event
  ↓
analytics-worker
  ↓
store metrics