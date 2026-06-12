#!/usr/bin/env bash
# Quick start script for ClickHouse performance testing
# Usage: ./performance_test_quickstart.sh [options]

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   ClickHouse Performance Testing - Quick Start      ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════╝${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}[1/4] Checking prerequisites...${NC}"

if ! command -v clickhouse-client &> /dev/null; then
    echo -e "${RED}✗ clickhouse-client not found${NC}"
    echo "Install with: sudo apt-get install clickhouse-client"
    exit 1
fi
echo -e "${GREEN}✓ clickhouse-client found${NC}"

if ! clickhouse-client --host localhost --query "SELECT 1" >/dev/null 2>&1; then
    echo -e "${RED}✗ ClickHouse not running on localhost:9000${NC}"
    echo "Start ClickHouse with: docker compose up -d clickhouse"
    exit 1
fi
echo -e "${GREEN}✓ ClickHouse is running${NC}"

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ python3 not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python 3 found${NC}"

# Create output directory
echo -e "${YELLOW}[2/4] Preparing...${NC}"
mkdir -p test/output
echo -e "${GREEN}✓ Output directory ready${NC}"

# Run performance tests
echo -e "${YELLOW}[3/4] Running performance tests...${NC}"
echo "This may take 5-10 minutes depending on your system."
echo ""

if python3 scripts/clickhouse/performance_test.py \
    --edges-per-source 10 \
    --output "test/output/performance_results.json"; then
    echo -e "${GREEN}✓ Tests completed${NC}"
else
    echo -e "${RED}✗ Tests failed${NC}"
    exit 1
fi

# Analyze results
echo ""
echo -e "${YELLOW}[4/4] Analyzing results...${NC}"

if python3 scripts/clickhouse/analyze_performance.py \
    --input test/output/performance_results.json \
    --output test/output/performance_report.txt \
    --html test/output/performance_report.html; then
    echo -e "${GREEN}✓ Analysis complete${NC}"
else
    echo -e "${RED}✗ Analysis failed${NC}"
    exit 1
fi

# Summary
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}PERFORMANCE TESTING COMPLETE!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
echo ""
echo "Results:"
echo "  JSON Metrics:  test/output/performance_results.json"
echo "  Text Report:   test/output/performance_report.txt"
echo "  HTML Report:   test/output/performance_report.html"
echo ""
echo "Next steps:"
echo "  1. View text report:"
echo "     cat test/output/performance_report.txt"
echo ""
echo "  2. Open HTML report in browser:"
echo "     • macOS:   open test/output/performance_report.html"
echo "     • Linux:   xdg-open test/output/performance_report.html"
echo "     • Windows: start test/output/performance_report.html"
echo ""
echo "For more options:"
echo "  python3 scripts/clickhouse/performance_test.py --help"
echo "  python3 scripts/clickhouse/analyze_performance.py --help"
echo ""
