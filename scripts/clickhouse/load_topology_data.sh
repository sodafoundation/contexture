#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <rows> [--prefix PREFIX] [--duration-minutes MINUTES]"
  echo "Examples:" 
  echo "  $0 100000" 
  echo "  $0 500000 --prefix mysvc --duration-minutes 120"
  exit 1
fi

NUM_ROWS="$1"
shift

# Keep the number of unique source workloads smaller than rows if only one edge per source.
NUM_SOURCES=$(( NUM_ROWS / 10 ))
if [ "$NUM_SOURCES" -lt 1 ]; then
  NUM_SOURCES=1
fi
EDGES_PER_SOURCE=10

python3 scripts/clickhouse/generate_topology_data.py \
  --num-sources "$NUM_SOURCES" \
  --edges-per-source "$EDGES_PER_SOURCE" \
  "$@" \
  | clickhouse-client --host localhost --query="INSERT INTO service_dependencies (source_workload, destination_workload, event_time) FORMAT CSV"

echo "Loaded topology rows into ClickHouse: approx $NUM_ROWS rows."
