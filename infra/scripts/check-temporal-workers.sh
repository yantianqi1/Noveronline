#!/bin/sh
set -eu

address="${TEMPORAL_ADDRESS:-temporal:7233}"
namespace="${TEMPORAL_NAMESPACE:-default}"
max_parallel="${TEMPORAL_READINESS_MAX_CONCURRENCY:-4}"

case "$max_parallel" in
  ''|*[!0-9]*) exit 1 ;;
esac
if [ "$max_parallel" -lt 1 ] || [ "$max_parallel" -gt 8 ]; then
  exit 1
fi

pids=""
batch_size=0
failed=0

wait_batch() {
  for pid in $pids; do
    if ! wait "$pid"; then
      failed=1
    fi
  done
  pids=""
  batch_size=0
}

for queue in maintenance seed-heavy asset-light graph-heavy worldline-interactive character-interactive writer-reviewer writer-planning writer-streaming analysis-streaming worldline-cast-streaming legacy-import; do
  for queue_type in workflow activity; do
    (
      output="$(temporal task-queue describe \
        --address "$address" \
        --namespace "$namespace" \
        --task-queue "$queue" \
        --task-queue-type "$queue_type" \
        --output json 2>/dev/null)"
      printf '%s' "$output" | grep -q '"identity"'
    ) &
    pids="$pids $!"
    batch_size=$((batch_size + 1))
    if [ "$batch_size" -ge "$max_parallel" ]; then
      wait_batch
    fi
  done
done

wait_batch
exit "$failed"
