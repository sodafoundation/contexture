#!/usr/bin/env python3
"""
ClickHouse Data Population & Performance Test Script
======================================================
Generates synthetic service-dependency data and runs query performance
benchmarks at 500 MB and 1 GB dataset sizes.

Usage:
    python scripts/clickhouse/populate_data.py 0.5   # populate 500 MB
    python scripts/clickhouse/populate_data.py 1.0   # populate 1 GB
    python scripts/clickhouse/populate_data.py test  # run only perf tests (no insert)

Requirements:
    pip install clickhouse-driver pyyaml
"""

import os
import sys
import time
import random
import logging
import yaml
from datetime import datetime, timedelta
from typing import List, Tuple, Dict
import clickhouse_driver

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.normpath(os.path.join(HERE, "..", "..", "config", "clickhouse_config.yaml"))

SERVICES = [
    "frontend", "backend", "api-gateway", "auth-service", "db",
    "cache", "queue", "notification", "analytics", "logging",
    "monitoring", "search", "storage", "payment", "user-service",
    "product-service", "order-service", "inventory", "shipping", "reporting",
]

BATCH_SIZE = 100_000   # rows per INSERT
AVG_ROW_BYTES = 100    # estimated uncompressed bytes per row


# ── Connection ────────────────────────────────────────────────────────────────

def load_config() -> Dict:
    if not os.path.exists(CONFIG_PATH):
        return {"host": "localhost", "port": 9000, "username": "default",
                "password": "", "database": "default"}
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    instances = cfg.get("clickhouse_instances", [{}])
    return instances[0]


def get_client(cfg: Dict) -> clickhouse_driver.Client:
    return clickhouse_driver.Client(
        host=cfg.get("host", "localhost"),
        port=cfg.get("port", 9000),
        user=cfg.get("username", "default"),
        password=cfg.get("password", ""),
        database=cfg.get("database", "default"),
    )


# ── Schema ────────────────────────────────────────────────────────────────────

def ensure_table(client: clickhouse_driver.Client):
    client.execute("""
        CREATE TABLE IF NOT EXISTS service_dependencies
        (
            source_workload      String,
            destination_workload String,
            event_time           DateTime
        )
        ENGINE = MergeTree()
        ORDER BY (source_workload, event_time)
    """)
    logger.info("Table service_dependencies ready.")


def truncate_table(client: clickhouse_driver.Client):
    client.execute("TRUNCATE TABLE service_dependencies")
    logger.info("Table truncated.")


# ── Data generation ───────────────────────────────────────────────────────────

def generate_batch(size: int) -> List[Tuple]:
    base = datetime.now() - timedelta(days=30)
    batch = []
    for _ in range(size):
        src = random.choice(SERVICES)
        dst = random.choice(SERVICES)
        while dst == src:
            dst = random.choice(SERVICES)
        t = base + timedelta(
            days=random.randint(0, 29),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
            seconds=random.randint(0, 59),
        )
        batch.append((src, dst, t))
    return batch


# ── Population ────────────────────────────────────────────────────────────────

def populate(client: clickhouse_driver.Client, target_gb: float) -> Dict:
    target_rows = int((target_gb * 1024 ** 3) / AVG_ROW_BYTES)
    logger.info(f"Target: {target_gb} GB  ≈  {target_rows:,} rows  (batch={BATCH_SIZE:,})")

    inserted = 0
    batches = 0
    t0 = time.time()

    while inserted < target_rows:
        this_batch = min(BATCH_SIZE, target_rows - inserted)
        data = generate_batch(this_batch)
        client.execute("INSERT INTO service_dependencies VALUES", data)
        inserted += this_batch
        batches += 1

        if batches % 5 == 0:
            elapsed = time.time() - t0
            rate = inserted / elapsed if elapsed else 0
            eta = (target_rows - inserted) / rate if rate else 0
            pct = 100.0 * inserted / target_rows
            logger.info(
                f"  {pct:5.1f}%  {inserted:>12,} rows  "
                f"{rate:>10,.0f} rows/s  ETA {eta/60:.1f} min"
            )

    elapsed = time.time() - t0

    # Retrieve final disk stats
    rows_q = client.execute("SELECT count() FROM service_dependencies")
    stats_q = client.execute(
        "SELECT total_rows, total_bytes, formatReadableSize(total_bytes), "
        "formatReadableSize(total_bytes_uncompressed) "
        "FROM system.tables WHERE table='service_dependencies'"
    )
    total_rows = rows_q[0][0] if rows_q else inserted
    disk_bytes, disk_str, uncomp_str = (
        (stats_q[0][1], stats_q[0][2], stats_q[0][3]) if stats_q
        else (0, "?", "?")
    )

    return {
        "target_gb": target_gb,
        "inserted_rows": inserted,
        "total_rows_in_table": total_rows,
        "elapsed_s": elapsed,
        "rows_per_sec": inserted / elapsed if elapsed else 0,
        "disk_bytes": disk_bytes,
        "disk_size": disk_str,
        "uncompressed_size": uncomp_str,
    }


# ── Performance benchmarks ────────────────────────────────────────────────────

BENCHMARK_QUERIES = {
    "count_all": "SELECT count() FROM service_dependencies",

    "group_by_source":
        "SELECT source_workload, count() AS cnt "
        "FROM service_dependencies "
        "GROUP BY source_workload ORDER BY cnt DESC",

    "group_by_pair":
        "SELECT source_workload, destination_workload, count() AS cnt "
        "FROM service_dependencies "
        "GROUP BY source_workload, destination_workload ORDER BY cnt DESC LIMIT 20",

    "last_7_days":
        "SELECT count() FROM service_dependencies "
        "WHERE event_time >= now() - INTERVAL 7 DAY",

    "last_1_day":
        "SELECT count() FROM service_dependencies "
        "WHERE event_time >= now() - INTERVAL 1 DAY",

    "distinct_sources":
        "SELECT count(DISTINCT source_workload) FROM service_dependencies",

    "top_pairs_last_week":
        "SELECT source_workload, destination_workload, count() AS cnt "
        "FROM service_dependencies "
        "WHERE event_time >= now() - INTERVAL 7 DAY "
        "GROUP BY source_workload, destination_workload "
        "ORDER BY cnt DESC LIMIT 10",

    "time_series_hourly":
        "SELECT toStartOfHour(event_time) AS hour, count() AS cnt "
        "FROM service_dependencies "
        "GROUP BY hour ORDER BY hour DESC LIMIT 48",
}


def run_benchmarks(client: clickhouse_driver.Client, runs: int = 3) -> Dict[str, Dict]:
    logger.info(f"\nRunning {len(BENCHMARK_QUERIES)} benchmark queries ({runs} runs each)...")
    results = {}

    for name, sql in BENCHMARK_QUERIES.items():
        times = []
        for _ in range(runs):
            t0 = time.time()
            client.execute(sql)
            times.append((time.time() - t0) * 1000)

        results[name] = {
            "min_ms":  round(min(times), 2),
            "avg_ms":  round(sum(times) / len(times), 2),
            "max_ms":  round(max(times), 2),
        }
        logger.info(f"  {name:<25}  avg={results[name]['avg_ms']:>8.1f} ms  "
                    f"min={results[name]['min_ms']:>8.1f} ms  max={results[name]['max_ms']:>8.1f} ms")

    return results


# ── Report generation ─────────────────────────────────────────────────────────

def build_report(pop: Dict, bench: Dict) -> str:
    sep = "=" * 72
    sub = "-" * 72

    lines = [
        sep,
        "  CLICKHOUSE PERFORMANCE REPORT",
        f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        sep,
        "",
        "INSERTION METRICS",
        sub,
        f"  Target size          : {pop['target_gb']:.2f} GB",
        f"  Rows inserted        : {pop['inserted_rows']:>15,}",
        f"  Total rows in table  : {pop['total_rows_in_table']:>15,}",
        f"  Elapsed time         : {pop['elapsed_s']:>14.1f} s  ({pop['elapsed_s']/60:.2f} min)",
        f"  Insertion rate       : {pop['rows_per_sec']:>14,.0f} rows/s",
        f"  Disk size (compressed): {pop['disk_size']:>14}",
        f"  Uncompressed size    : {pop['uncompressed_size']:>14}",
        "",
        "QUERY PERFORMANCE BENCHMARKS  (3 runs each)",
        sub,
        f"  {'Query':<25}  {'avg ms':>9}  {'min ms':>9}  {'max ms':>9}",
        f"  {'-'*25}  {'-'*9}  {'-'*9}  {'-'*9}",
    ]

    for name, r in bench.items():
        grade = (
            "🟢 fast"   if r["avg_ms"] < 200  else
            "🟡 ok"     if r["avg_ms"] < 1000 else
            "🔴 slow"
        )
        lines.append(
            f"  {name:<25}  {r['avg_ms']:>9.1f}  {r['min_ms']:>9.1f}  {r['max_ms']:>9.1f}  {grade}"
        )

    lines += [
        "",
        "COMPRESSION ANALYSIS",
        sub,
    ]
    if pop["disk_bytes"] and pop["inserted_rows"]:
        bytes_per_row = pop["disk_bytes"] / pop["inserted_rows"]
        lines.append(f"  Avg compressed bytes/row : {bytes_per_row:.2f} bytes")
        uncomp_bytes = pop["inserted_rows"] * AVG_ROW_BYTES
        ratio = uncomp_bytes / pop["disk_bytes"] if pop["disk_bytes"] else 0
        lines.append(f"  Compression ratio        : {ratio:.1f}x")

    lines += ["", sep, ""]
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "0.5"
    test_only = arg.lower() == "test"
    target_gb = float(arg) if not test_only else 0.0

    cfg = load_config()
    logger.info(f"Connecting to ClickHouse at {cfg.get('host')}:{cfg.get('port', 9000)} ...")

    try:
        client = get_client(cfg)
        client.execute("SELECT 1")
        logger.info("Connection OK.")
    except Exception as e:
        logger.error(f"Cannot connect to ClickHouse: {e}")
        logger.error("Make sure ClickHouse is running:  docker-compose up -d clickhouse")
        sys.exit(1)

    ensure_table(client)

    if not test_only:
        truncate_table(client)
        logger.info(f"\n{'='*60}")
        logger.info(f"  Populating {target_gb} GB of data...")
        logger.info(f"{'='*60}")
        pop_result = populate(client, target_gb)
        logger.info(
            f"\nInsertion complete: {pop_result['inserted_rows']:,} rows in "
            f"{pop_result['elapsed_s']:.1f}s ({pop_result['rows_per_sec']:,.0f} rows/s)"
        )
    else:
        # test_only: just grab current table stats
        rows_q = client.execute("SELECT count() FROM service_dependencies")
        stats_q = client.execute(
            "SELECT total_rows, total_bytes, formatReadableSize(total_bytes), "
            "formatReadableSize(total_bytes_uncompressed) "
            "FROM system.tables WHERE table='service_dependencies'"
        )
        pop_result = {
            "target_gb": 0,
            "inserted_rows": 0,
            "total_rows_in_table": rows_q[0][0] if rows_q else 0,
            "elapsed_s": 0,
            "rows_per_sec": 0,
            "disk_bytes": stats_q[0][1] if stats_q else 0,
            "disk_size": stats_q[0][2] if stats_q else "?",
            "uncompressed_size": stats_q[0][3] if stats_q else "?",
        }

    bench_results = run_benchmarks(client)
    report = build_report(pop_result, bench_results)

    print("\n" + report)

    # Save report
    label = "test_only" if test_only else f"{target_gb}gb"
    fname = f"clickhouse_perf_report_{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    fpath = os.path.join(HERE, "..", "..", fname)
    fpath = os.path.normpath(fpath)
    with open(fpath, "w") as f:
        f.write(report)
    logger.info(f"Report saved → {fpath}")


if __name__ == "__main__":
    main()
