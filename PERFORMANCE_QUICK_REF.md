# ClickHouse Performance Testing - Quick Reference

## One-Command Start
```bash
./performance_test_quickstart.sh
```

## File Structure
```
📂 Root
├── 🟢 performance_test_quickstart.sh       ← START HERE
├── PERFORMANCE_TESTING_SETUP.md            ← Setup guide
└── 📂 scripts/clickhouse/
    ├── performance_test.py                 ← Main tester
    ├── analyze_performance.py              ← Report generator
    ├── run_performance_test.sh             ← Bash wrapper
    └── PERFORMANCE_TESTING.md              ← Full docs
```

## Test Datasets Generated
| Size | Rows | Load Time | Throughput |
|------|------|-----------|-----------|
| 500MB | ~9M | 30-120s | 100K-300K rows/s |
| 1GB | ~18M | 60-240s | 100K-300K rows/s |

## Output Files
```
test/output/
├── performance_results.json        (raw metrics)
├── performance_report.txt          (text analysis)
└── performance_report.html         (interactive charts)
```

## Common Commands

### Run All Tests (500MB + 1GB)
```bash
./performance_test_quickstart.sh
```

### Test Only 500MB
```bash
python3 scripts/clickhouse/performance_test.py --skip-1gb
```

### Test Only 1GB
```bash
python3 scripts/clickhouse/performance_test.py --skip-1gb
```

### Custom Dataset
```bash
python3 scripts/clickhouse/performance_test.py --custom-size 5000000
```

### More Complex Topology (20 edges/source)
```bash
python3 scripts/clickhouse/performance_test.py --edges-per-source 20
```

### View Text Report
```bash
cat test/output/performance_report.txt
```

### View HTML Report (Interactive)
```bash
# Linux
xdg-open test/output/performance_report.html

# macOS
open test/output/performance_report.html

# Windows
start test/output/performance_report.html
```

### Regenerate Report Only
```bash
python3 scripts/clickhouse/analyze_performance.py
```

## Prerequisites Check
```bash
# ClickHouse running?
clickhouse-client --host localhost --query "SELECT 1"

# Python installed?
python3 --version

# Client installed?
which clickhouse-client
```

## Queries Measured
- Count all rows
- Distinct sources
- Distinct destinations
- Top 10 sources (by count)
- Top 10 destinations (by count)
- Time-range queries (30 min window)

## Expected Performance
```
500MB Dataset:
  Load: 200K rows/sec average
  Table: 500.50 MB actual
  Queries: <500ms each
  
1GB Dataset:
  Load: 200K rows/sec average
  Table: 1001.25 MB actual
  Queries: <1s each
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| ClickHouse not running | `docker compose up -d clickhouse` |
| `clickhouse-client` not found | `sudo apt-get install clickhouse-client` |
| Permission denied | `chmod +x *.sh` |
| Out of memory | Use `--custom-size 1000000` for smaller dataset |
| Slow performance | Check disk space, CPU usage, RAM available |

## Environment Variables

Optional - set before running tests:
```bash
# Use different ClickHouse host
export CLICKHOUSE_HOST=192.168.1.100

# Use different port
export CLICKHOUSE_PORT=9001
```

## Python Options

```bash
python3 scripts/clickhouse/performance_test.py \
  --edges-per-source 10           # edges per source (default: 10)
  --output results.json           # output file (default: performance_results.json)
  --custom-size 5000000           # custom row count
  --skip-500mb                    # skip 500MB test
  --skip-1gb                      # skip 1GB test
```

## What Gets Tested
✓ Data generation (Python)  
✓ Load performance (ingestion speed)  
✓ Compression ratio  
✓ Query performance (6 different queries)  
✓ Table metrics (size, row count)  

## Schema Used
```sql
CREATE TABLE service_dependencies (
    source_workload String,           -- calling service
    destination_workload String,      -- called service
    event_time DateTime               -- when called
)
ENGINE = MergeTree()
ORDER BY (source_workload, event_time)
```

## Integration with OCS
```bash
# Run performance tests (loads data)
./performance_test_quickstart.sh

# Start OCS with ClickHouse backend
export CONNECTOR=clickhouse
./ocs-server &

# Use OCS
python3 scripts/run_sample_queries.py --mode ocs
```

---
For full documentation, see: `PERFORMANCE_TESTING_SETUP.md`
