# ClickHouse Performance Testing Setup Complete ✓

## What Was Created

I've set up a complete performance testing suite for ClickHouse with 500MB and 1GB datasets. Here's what's included:

### Scripts Created

1. **`scripts/clickhouse/performance_test.py`** (Main Testing Engine)
   - Generates synthetic service dependency data
   - Loads data into ClickHouse and measures throughput
   - Runs 6 standard performance queries
   - Calculates compression metrics
   - Outputs JSON results

2. **`scripts/clickhouse/analyze_performance.py`** (Analysis & Reporting)
   - Analyzes performance metrics
   - Generates text and HTML reports
   - Creates interactive charts with Chart.js
   - Provides performance recommendations

3. **`scripts/clickhouse/run_performance_test.sh`** (Automated Testing)
   - Verifies ClickHouse is running
   - Runs the Python test suite
   - Handles errors gracefully

4. **`performance_test_quickstart.sh`** (One-Click Testing)
   - Single command to run everything
   - Checks all prerequisites
   - Runs tests and generates reports

5. **`scripts/clickhouse/PERFORMANCE_TESTING.md`** (Documentation)
   - Complete user guide
   - Advanced usage examples
   - Troubleshooting tips
   - Integration with OCS

## Quick Start (3 Steps)

### Step 1: Ensure ClickHouse is Running

```bash
docker compose up -d clickhouse
docker compose run --rm clickhouse-init
```

Verify:
```bash
clickhouse-client --host localhost --query "SELECT 1"
```

### Step 2: Run Performance Tests

**Option A - Quickest Way (One Command):**
```bash
./performance_test_quickstart.sh
```

**Option B - Direct Python:**
```bash
python3 scripts/clickhouse/performance_test.py
```

**Option C - Via Bash Script:**
```bash
./scripts/clickhouse/run_performance_test.sh
```

### Step 3: View Results

The tests will generate three files in `test/output/`:
- `performance_results.json` - Raw metrics
- `performance_report.txt` - Detailed text analysis
- `performance_report.html` - Interactive HTML report

View the text report:
```bash
cat test/output/performance_report.txt
```

Or open the HTML report in a browser:
```bash
# Linux
xdg-open test/output/performance_report.html

# macOS
open test/output/performance_report.html

# Windows
start test/output/performance_report.html
```

## What Gets Tested

### Datasets
- **500MB Dataset**: ~9 million rows
- **1GB Dataset**: ~18 million rows

### Metrics Collected
- Load time (seconds)
- Throughput (rows/second)
- Table size (MB)
- Compression ratio (rows/MB)
- Query execution times for:
  - Full row count
  - Distinct source workloads
  - Distinct destination workloads
  - Top 10 busiest sources
  - Top 10 busiest destinations
  - Time-range queries (last 30 minutes)

## Advanced Usage

### Generate Only 500MB (Skip 1GB)
```bash
python3 scripts/clickhouse/performance_test.py --skip-1gb
```

### Generate Only 1GB (Skip 500MB)
```bash
python3 scripts/clickhouse/performance_test.py --skip-500mb
```

### Custom Dataset Size
```bash
python3 scripts/clickhouse/performance_test.py --custom-size 5000000
```

### Adjust Topology Complexity
```bash
# More edges per source = denser topology
python3 scripts/clickhouse/performance_test.py --edges-per-source 20
```

### Custom Output Location
```bash
python3 scripts/clickhouse/performance_test.py --output my_results.json
python3 scripts/clickhouse/analyze_performance.py --input my_results.json
```

## Expected Output

When you run the tests, you'll see output like:

```
============================================================
Loading 500MB Dataset: ~9,000,000 rows
============================================================
Generating 900,000 sources with 10 edges each...
✓ Data loaded in 45.23 seconds
Actual rows: 9,000,000
Table size: 500.50 MB
Throughput: 198,987 rows/sec

Running performance queries...
  count_all: 0.142s
  distinct_sources: 0.156s
  distinct_destinations: 0.148s
  top_sources: 0.182s
  top_destinations: 0.175s
  time_range_query: 0.098s
```

## Performance Expectations

Based on typical hardware:

### Load Performance
- **Throughput**: 100K-300K rows/second (depending on CPU/disk)
- **500MB**: 30-120 seconds to load
- **1GB**: 60-240 seconds to load

### Query Performance
- **Simple counts**: 100-200ms
- **GROUP BY queries**: 150-300ms
- **Complex queries**: 200-500ms

### Compression
- **Typical ratio**: 500K-1M rows per MB
- **Varies based on**: column distinctness, data distribution, compression settings

## Troubleshooting

### ClickHouse Not Running
```bash
docker compose up -d clickhouse
docker compose logs -f clickhouse
```

### Connection Refused
```bash
netstat -tlnp | grep 9000
# Should show something listening on :9000
```

### No `clickhouse-client`
```bash
# Ubuntu/Debian
sudo apt-get install clickhouse-client

# macOS
brew install clickhouse
```

### Out of Memory
Try smaller dataset:
```bash
python3 scripts/clickhouse/performance_test.py --custom-size 1000000
```

### Permission Denied
```bash
chmod +x performance_test_quickstart.sh
chmod +x scripts/clickhouse/run_performance_test.sh
```

## File Locations

```
contexture-main/
├── performance_test_quickstart.sh          (🟢 Main entry point)
├── scripts/clickhouse/
│   ├── performance_test.py                 (Core testing logic)
│   ├── analyze_performance.py              (Analysis & reporting)
│   ├── run_performance_test.sh             (Bash wrapper)
│   └── PERFORMANCE_TESTING.md              (Full documentation)
└── test/output/
    ├── performance_results.json            (Generated - raw data)
    ├── performance_report.txt              (Generated - analysis)
    └── performance_report.html             (Generated - interactive)
```

## Integration with Your Workflow

### With OCS
After generating data, you can use it with OCS:

```bash
# Load test data (already done by performance tests)
python3 scripts/clickhouse/performance_test.py

# Start OCS with ClickHouse backend
export CONNECTOR=clickhouse
export MONGODB_URI=memory
./ocs-server &

# Run OCS queries
python3 scripts/run_sample_queries.py --mode ocs
```

### With Your Application
The generated data follows the schema:
- `source_workload` (STRING): Name of calling service
- `destination_workload` (STRING): Name of called service
- `event_time` (DATETIME): When the call occurred

Perfect for testing topology-based applications at scale!

## Next Steps

1. **Run the quick-start**:
   ```bash
   ./performance_test_quickstart.sh
   ```

2. **Review the text report**:
   ```bash
   cat test/output/performance_report.txt
   ```

3. **Open HTML report in browser** for interactive charts

4. **Experiment with different parameters**:
   ```bash
   python3 scripts/clickhouse/performance_test.py --custom-size 3000000
   ```

5. **Compare results** by running tests multiple times and checking differences

## Performance Optimization Tips

### For Faster Loading
- Use SSD instead of HDD
- Increase RAM for ClickHouse caching
- Run tests when system is idle
- Use more CPU cores

### For Faster Queries
- Add indexes on frequently filtered columns
- Use MATERIALIZED VIEWS for common aggregations
- Partition data by date/time
- Use PREWHERE clause for large datasets

### For Smaller Table Size
- Use compression algorithms (ZSTD, LZ4)
- Store timestamps as compact formats
- Use shorter column names internally
- Use dictionary encoding for repeated strings

## Getting Help

For more detailed information:
- Read: `scripts/clickhouse/PERFORMANCE_TESTING.md`
- Check: `docs/CLICKHOUSE.md` for general setup
- See: ClickHouse docs at https://clickhouse.com/docs/

---

**Created**: 2026-06-12  
**Status**: Ready to use ✓
