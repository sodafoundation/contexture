# ClickHouse Performance Testing Guide

This directory contains tools for testing ClickHouse performance with 500MB and 1GB datasets.

## Overview

The performance testing suite includes:
- **Data Generation**: Python script to generate large synthetic datasets
- **Performance Testing**: Automated testing framework with load and query benchmarking
- **Analysis**: Visualization and analysis tools to interpret results

## Prerequisites

1. **ClickHouse Running**:
   ```bash
   docker compose up -d clickhouse
   ```

2. **ClickHouse Client**:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install clickhouse-client
   
   # macOS
   brew install clickhouse
   ```

3. **Python 3.8+** with no additional dependencies required

## Quick Start

### 1. Run Full Performance Test (500MB + 1GB)

```bash
./scripts/clickhouse/run_performance_test.sh
```

This will:
- Generate 500MB dataset (~9M rows)
- Load and benchmark
- Generate 1GB dataset (~18M rows)
- Load and benchmark
- Save results to `test/output/performance_results.json`

### 2. Analyze Results

```bash
python3 scripts/clickhouse/analyze_performance.py
```

This generates:
- Console report with detailed metrics
- Text report: `test/output/performance_report.txt`
- HTML report: `test/output/performance_report.html` (with charts)

### 3. View HTML Report

Open `test/output/performance_report.html` in a web browser to see interactive charts.

## Advanced Usage

### Custom Dataset Size

```bash
python3 scripts/clickhouse/performance_test.py --custom-size 5000000
```

Generate a custom dataset with 5 million rows.

### Skip Specific Datasets

```bash
# Test only 1GB
python3 scripts/clickhouse/performance_test.py --skip-500mb

# Test only 500MB
python3 scripts/clickhouse/performance_test.py --skip-1gb
```

### Configure Edges Per Source

```bash
# More complex topology (20 edges per source)
python3 scripts/clickhouse/performance_test.py --edges-per-source 20
```

Lower edges = more sources. Higher edges = denser topology.

### Full End-to-End Workflow

```bash
# 1. Run tests
./scripts/clickhouse/run_performance_test.sh

# 2. Analyze results
python3 scripts/clickhouse/analyze_performance.py

# 3. View browser report
open test/output/performance_report.html  # macOS
xdg-open test/output/performance_report.html  # Linux
start test/output/performance_report.html  # Windows
```

## Script Details

### `performance_test.py`

Main performance testing script.

**What it does:**
1. Generates CSV data using the Python generator
2. Streams data to ClickHouse via `clickhouse-client`
3. Measures load time and throughput
4. Runs standard queries and measures execution time
5. Collects actual table metrics from ClickHouse

**Queries measured:**
- Count all rows
- Count distinct sources
- Count distinct destinations
- Top 10 sources (by edge count)
- Top 10 destinations (by edge count)
- Time range query (last 30 minutes)

**Output:** JSON file with comprehensive metrics

### `analyze_performance.py`

Analyzes test results and generates reports.

**Features:**
- Detailed performance metrics
- Query performance analysis
- Performance recommendations
- HTML visualization with Chart.js
- Compression ratio analysis
- Dataset comparison metrics

### `run_performance_test.sh`

Bash wrapper that:
- Verifies ClickHouse is running
- Runs the Python performance test
- Handles error cases

## Expected Results

### 500MB Dataset
- **Rows**: ~9 million
- **Load Time**: Varies by hardware (typically 30-120 seconds)
- **Throughput**: 75K-300K rows/second
- **Query Times**: Typically <1 second for simple queries

### 1GB Dataset
- **Rows**: ~18 million
- **Load Time**: Varies by hardware (typically 60-240 seconds)
- **Throughput**: Similar to 500MB if linear scaling
- **Query Times**: Typically <2-3 seconds

### Compression Ratio
- Typical: 500K-1M rows per MB
- Data includes: source, destination, timestamp
- MergeTree compression varies based on column distribution

## Troubleshooting

### ClickHouse Not Running
```bash
docker compose up -d clickhouse
docker compose run --rm clickhouse-init
```

### Permission Denied
```bash
chmod +x scripts/clickhouse/run_performance_test.sh
```

### Connection Refused
```bash
# Check if ClickHouse is listening
netstat -tlnp | grep 9000

# Or test connection
clickhouse-client --host localhost --query "SELECT 1"
```

### Out of Memory
Try smaller dataset:
```bash
python3 scripts/clickhouse/performance_test.py --custom-size 1000000
```

### Slow Performance
- Check available disk space
- Monitor ClickHouse process: `docker stats`
- Check CPU usage during load
- Reduce `edges-per-source` for smaller topology

## Performance Tuning

### System Settings
- **RAM**: More RAM = better caching performance
- **SSD**: Better I/O performance than HDD
- **CPU Cores**: More cores = better parallel query execution

### ClickHouse Config
- Increase `max_insert_threads` for faster inserts
- Tune `background_buffer_flush_schedule_pool_size`
- Adjust `max_concurrent_queries`

### Data Generation
- More edges per source = denser topology
- More sources = wider dataset
- Time distribution affects query performance

## Output Files

```
test/output/
├── performance_results.json       # Raw metrics
├── performance_report.txt         # Text analysis
└── performance_report.html        # Interactive HTML report
```

## Integration with OCS

The generated data can be used with OCS (Observation Context System):

```bash
# After loading data
export CONNECTOR=clickhouse
export MONGODB_URI=memory
./ocs-server &

# Run OCS queries
python3 scripts/run_sample_queries.py --mode ocs
```

## Additional Resources

- [ClickHouse Documentation](https://clickhouse.com/docs/)
- [MergeTree Documentation](https://clickhouse.com/docs/en/engines/table-engines/mergetree-family/mergetree/)
- See [CLICKHOUSE.md](../../docs/CLICKHOUSE.md) for general setup

## Example Performance Report

```
==============================================================================
PERFORMANCE TEST SUMMARY
==============================================================================

Test 1: 500.50 MB
  Rows: 9,000,000
  Load Time: 45.23s
  Throughput: 198,987 rows/sec
  Table Size: 500.50 MB
  Queries:
    count_all: 0.142s
    distinct_sources: 0.156s
    distinct_destinations: 0.148s
    top_sources: 0.182s
    top_destinations: 0.175s
    time_range_query: 0.098s

Test 2: 1001.25 MB
  Rows: 18,000,000
  Load Time: 89.15s
  Throughput: 201,885 rows/sec
  Table Size: 1001.25 MB
  Queries:
    count_all: 0.198s
    distinct_sources: 0.211s
    distinct_destinations: 0.203s
    top_sources: 0.241s
    top_destinations: 0.233s
    time_range_query: 0.127s
```

## Contributing

To add new benchmark queries, edit `run_performance_queries()` in `performance_test.py`.
