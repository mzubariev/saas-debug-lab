#!/usr/bin/env bash
# Produce duplicate Kafka messages (same business payload) to task_created.
# Uses host python3 for JSON envelope. Env: CHAOS_DUPLICATE_COUNT (default 3), KAFKA_TOPIC (default task_created)
set -euo pipefail

COUNT="${CHAOS_DUPLICATE_COUNT:-3}"
TOPIC="${KAFKA_TOPIC:-task_created}"
TID="${CHAOS_TASK_ID:-00000000-0000-4000-8000-00000000cafe}"

echo "[CHAOS] Running duplicate_events"
echo "[CHAOS] duplicate_events: ${COUNT} copies → ${TOPIC} (task_id=${TID})"
MSG="$(
  python3 -c "
import json, uuid
from datetime import datetime, timezone
p = {'id': '${TID}', 'title': 'chaos-duplicate', 'status': 'created'}
env = {
  'event_type': 'task.created',
  'version': 'v1',
  'trace_id': uuid.uuid4().hex,
  'timestamp': datetime.now(timezone.utc).isoformat(),
  'payload': p,
}
print(json.dumps(env))
")"

for _ in $(seq 1 "$COUNT"); do
  echo "$MSG" | docker exec -i kafka kafka-console-producer --bootstrap-server kafka:9092 --topic "$TOPIC" >/dev/null
done
echo "[CHAOS] duplicate_events: sent ${COUNT} messages"
