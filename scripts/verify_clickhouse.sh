#!/usr/bin/env bash
# Start dependencies, build OCS server with ClickHouse connector, and smoke-test APIs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if command -v docker >/dev/null 2>&1; then
  echo "==> Starting MongoDB and ClickHouse (docker compose)..."
  docker compose up -d mongodb clickhouse
  docker compose run --rm clickhouse-init
  export MONGODB_URI="${MONGODB_URI:-mongodb://localhost:27017/}"
else
  echo "==> Docker not found; using in-memory store (MONGODB_URI=memory)."
  echo "    Start ClickHouse separately (see docs/CLICKHOUSE.md) or: docker compose up -d clickhouse"
  export MONGODB_URI=memory
fi

echo "==> Building OCS server..."
if ! command -v go >/dev/null 2>&1; then
  echo "Go is not installed. Install Go 1.21+ or use the prebuilt binary with CONNECTOR=clickhouse."
  exit 1
fi
go get github.com/ClickHouse/clickhouse-go/v2@latest
go build -o ocs-server ./pkg/ocs/

echo "==> Starting server (CONNECTOR=clickhouse)..."
export CONNECTOR=clickhouse
export PORT=8000
./ocs-server &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT

for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "==> Health check"
curl -s http://localhost:8000/health | python3 -m json.tool

echo "==> Collect topology from ClickHouse"
curl -s -X POST http://localhost:8000/collect_topology | python3 -m json.tool

echo "==> OCS prompt (context from MongoDB + config)"
curl -s http://localhost:8000/get_ocs_prompt | python3 -m json.tool

echo ""
echo "Verification complete. Server was running on http://localhost:8000 (pid $SERVER_PID)."
