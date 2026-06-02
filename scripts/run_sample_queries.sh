#!/usr/bin/env bash
# Run OCS sample queries (ClickHouse backend). Ensures server is up if possible.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! curl -sf http://localhost:8000/health >/dev/null 2>&1; then
  echo "OCS server not running. Starting with ClickHouse connector..."
  if ! ss -tlnp 2>/dev/null | grep -q ':9000'; then
    echo "ClickHouse not on :9000. Start ClickHouse first (see docs/CLICKHOUSE.md)."
    exit 1
  fi
  export CONNECTOR=clickhouse
  export MONGODB_URI=memory
  export PORT=8000
  ./ocs-server &
  sleep 3
fi

python3 scripts/run_sample_queries.py --mode ocs "$@"
