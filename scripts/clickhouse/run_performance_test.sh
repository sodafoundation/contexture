#!/usr/bin/env bash
# Run ClickHouse performance tests for 500MB and 1GB datasets
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

# Check if ClickHouse is running
if ! clickhouse-client --host localhost --query "SELECT 1" >/dev/null 2>&1; then
    echo "Error: ClickHouse is not running on localhost:9000"
    echo "Start ClickHouse first:"
    echo "  docker compose up -d clickhouse"
    exit 1
fi

echo "ClickHouse Performance Testing Suite"
echo "===================================="
echo ""

# Run the performance test
python3 scripts/clickhouse/performance_test.py \
    --edges-per-source 10 \
    --output "test/output/performance_results.json" \
    "$@"

echo ""
echo "Results saved to test/output/performance_results.json"
