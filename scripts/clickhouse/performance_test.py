#!/usr/bin/env python3
"""
ClickHouse Performance Testing Suite
Generates datasets (500MB, 1GB) and analyzes query performance.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import random
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PerformanceMetrics:
    """Store performance metrics for a test run."""
    dataset_size_mb: float
    num_rows: int
    load_time_seconds: float
    table_size_mb: float
    query_times: dict[str, float]
    rows_per_second: float


def get_clickhouse_size(table_name: str = "service_dependencies") -> float:
    """Get the actual table size in MB from ClickHouse."""
    try:
        cmd = ["clickhouse-client", "--host", "localhost"]
        # include credentials if provided via environment
        ch_user = os.environ.get("CLICKHOUSE_USER")
        ch_pass = os.environ.get("CLICKHOUSE_PASSWORD")
        if ch_user:
            cmd += ["--user", ch_user]
        if ch_pass:
            cmd += ["--password", ch_pass]
        cmd += ["--query", f"SELECT formatReadableSize(total_bytes) FROM system.tables WHERE name = '{table_name}'"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            output = result.stdout.strip()
            # Parse output like "10.5 MiB" or "1.0 GiB"
            if "GiB" in output:
                return float(output.split()[0]) * 1024
            elif "MiB" in output:
                return float(output.split()[0])
            elif "B" in output:
                return float(output.split()[0]) / (1024 * 1024)
    except Exception as e:
        print(f"Warning: Could not get table size: {e}")
    return 0.0


def get_row_count(table_name: str = "service_dependencies") -> int:
    """Get the number of rows in the table."""
    try:
        cmd = ["clickhouse-client", "--host", "localhost"]
        ch_user = os.environ.get("CLICKHOUSE_USER")
        ch_pass = os.environ.get("CLICKHOUSE_PASSWORD")
        if ch_user:
            cmd += ["--user", ch_user]
        if ch_pass:
            cmd += ["--password", ch_pass]
        cmd += ["--query", f"SELECT count() FROM {table_name}"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return int(result.stdout.strip())
    except Exception as e:
        print(f"Warning: Could not get row count: {e}")
    return 0


def build_workloads(prefix: str, count: int) -> list[str]:
    """Generate workload names."""
    return [f"{prefix}-{i:05d}" for i in range(1, count + 1)]


def generate_csv_data(
    num_sources: int,
    edges_per_source: int,
    duration_minutes: int = 60,
    start_time: datetime.datetime | None = None,
    prefix: str = "service",
    seed: int = 42,
) -> None:
    """Generate CSV topology data and write to stdout."""
    if start_time is None:
        start_time = datetime.datetime.utcnow() - datetime.timedelta(hours=1)

    random.seed(seed)
    sources = build_workloads(prefix, num_sources)
    total = len(sources)
    writer = csv.writer(sys.stdout, lineterminator="\n")

    for source in sources:
        destinations = random.sample(sources, k=min(edges_per_source + 1, total))
        if source in destinations:
            destinations.remove(source)
        if len(destinations) > edges_per_source:
            destinations = destinations[:edges_per_source]

        for destination in destinations:
            offset_seconds = random.randint(0, max(duration_minutes * 60 - 1, 0))
            event_time = start_time + datetime.timedelta(seconds=offset_seconds)
            writer.writerow([
                source,
                destination,
                event_time.strftime("%Y-%m-%d %H:%M:%S"),
            ])


def load_data_to_clickhouse(
    num_rows: int,
    dataset_label: str = "dataset",
    edges_per_source: int = 10,
    table_name: str = "service_dependencies",
) -> PerformanceMetrics:
    """Generate and load data to ClickHouse, measuring performance."""
    print(f"\n{'='*60}")
    print(f"Loading {dataset_label}: ~{num_rows:,} rows")
    print(f"{'='*60}")

    # Calculate number of sources based on rows and edges
    num_sources = max(1, num_rows // edges_per_source)

    print(f"Generating {num_sources:,} sources with {edges_per_source} edges each...")
    start_time = time.time()

    # Generate data
    gen_process = subprocess.Popen(
        [
            sys.executable, "-c",
            f"""
import sys
sys.path.insert(0, '/home/niteesh/contexture-main')
from scripts.clickhouse.performance_test import generate_csv_data
generate_csv_data(
    num_sources={num_sources},
    edges_per_source={edges_per_source},
    prefix='svc',
)
"""
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Stream to ClickHouse
    # build clickhouse-client command with optional credentials
    ch_cmd = ["clickhouse-client", "--host", "localhost"]
    ch_user = os.environ.get("CLICKHOUSE_USER")
    ch_pass = os.environ.get("CLICKHOUSE_PASSWORD")
    if ch_user:
        ch_cmd += ["--user", ch_user]
    if ch_pass:
        ch_cmd += ["--password", ch_pass]
    ch_cmd += ["--query", f"INSERT INTO {table_name} (source_workload, destination_workload, event_time) FORMAT CSV"]

    insert_process = subprocess.Popen(
        ch_cmd,
        stdin=gen_process.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    gen_process.stdout.close()
    insert_process.wait()
    gen_output, gen_error = gen_process.communicate()

    if insert_process.returncode != 0:
        _, insert_error = insert_process.communicate()
        print(f"Error loading data: {insert_error}")
        raise RuntimeError(f"ClickHouse insert failed: {insert_error}")

    load_time = time.time() - start_time
    print(f"✓ Data loaded in {load_time:.2f} seconds")

    # Get actual metrics
    time.sleep(2)  # Give ClickHouse time to finalize
    actual_rows = get_row_count(table_name)
    actual_size = get_clickhouse_size(table_name)
    rows_per_sec = actual_rows / load_time if load_time > 0 else 0

    print(f"Actual rows: {actual_rows:,}")
    print(f"Table size: {actual_size:.2f} MB")
    print(f"Throughput: {rows_per_sec:,.0f} rows/sec")

    # Run performance queries
    print(f"\nRunning performance queries...")
    query_times = run_performance_queries(table_name)

    metrics = PerformanceMetrics(
        dataset_size_mb=actual_size,
        num_rows=actual_rows,
        load_time_seconds=load_time,
        table_size_mb=actual_size,
        query_times=query_times,
        rows_per_second=rows_per_sec,
    )

    return metrics


def run_performance_queries(table_name: str = "service_dependencies") -> dict[str, float]:
    """Run sample queries and measure execution time."""
    queries = {
        "count_all": f"SELECT count() FROM {table_name}",
        "distinct_sources": f"SELECT count(DISTINCT source_workload) FROM {table_name}",
        "distinct_destinations": f"SELECT count(DISTINCT destination_workload) FROM {table_name}",
        "top_sources": f"SELECT source_workload, count() as cnt FROM {table_name} GROUP BY source_workload ORDER BY cnt DESC LIMIT 10",
        "top_destinations": f"SELECT destination_workload, count() as cnt FROM {table_name} GROUP BY destination_workload ORDER BY cnt DESC LIMIT 10",
        "time_range_query": f"SELECT count() FROM {table_name} WHERE event_time >= now() - INTERVAL 30 MINUTE",
    }

    query_times = {}
    for name, query in queries.items():
        try:
            start = time.time()
            cmd = ["clickhouse-client", "--host", "localhost"]
            ch_user = os.environ.get("CLICKHOUSE_USER")
            ch_pass = os.environ.get("CLICKHOUSE_PASSWORD")
            if ch_user:
                cmd += ["--user", ch_user]
            if ch_pass:
                cmd += ["--password", ch_pass]
            cmd += ["--query", query]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            elapsed = time.time() - start

            if result.returncode == 0:
                query_times[name] = elapsed
                print(f"  {name}: {elapsed:.3f}s")
            else:
                print(f"  {name}: ERROR - {result.stderr}")
        except Exception as e:
            print(f"  {name}: TIMEOUT/ERROR - {e}")

    return query_times


def clear_table(table_name: str = "service_dependencies") -> None:
    """Clear the table before loading new data."""
    try:
        cmd = ["clickhouse-client", "--host", "localhost"]
        ch_user = os.environ.get("CLICKHOUSE_USER")
        ch_pass = os.environ.get("CLICKHOUSE_PASSWORD")
        if ch_user:
            cmd += ["--user", ch_user]
        if ch_pass:
            cmd += ["--password", ch_pass]
        cmd += ["--query", f"TRUNCATE TABLE {table_name}"]
        subprocess.run(cmd, check=True, capture_output=True, timeout=10)
        time.sleep(1)
        print(f"✓ Table {table_name} cleared")
    except Exception as e:
        print(f"Warning: Could not clear table: {e}")


def save_metrics(metrics_list: list[PerformanceMetrics], output_file: str) -> None:
    """Save metrics to a JSON file."""
    data = {
        "timestamp": datetime.datetime.now().isoformat(),
        "tests": [
            {
                "dataset_size_mb": m.dataset_size_mb,
                "num_rows": m.num_rows,
                "load_time_seconds": m.load_time_seconds,
                "table_size_mb": m.table_size_mb,
                "rows_per_second": m.rows_per_second,
                "query_times": m.query_times,
            }
            for m in metrics_list
        ],
    }

    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\n✓ Metrics saved to {output_file}")


def print_summary(metrics_list: list[PerformanceMetrics]) -> None:
    """Print a summary of all test runs."""
    print(f"\n{'='*60}")
    print("PERFORMANCE TEST SUMMARY")
    print(f"{'='*60}")

    for i, metrics in enumerate(metrics_list, 1):
        print(f"\nTest {i}: {metrics.dataset_size_mb:.2f} MB")
        print(f"  Rows: {metrics.num_rows:,}")
        print(f"  Load Time: {metrics.load_time_seconds:.2f}s")
        print(f"  Throughput: {metrics.rows_per_second:,.0f} rows/sec")
        print(f"  Table Size: {metrics.table_size_mb:.2f} MB")
        print(f"  Queries:")
        for query_name, query_time in metrics.query_times.items():
            print(f"    {query_name}: {query_time:.3f}s")


def main() -> int:
    parser = argparse.ArgumentParser(description="ClickHouse Performance Testing Suite")
    parser.add_argument(
        "--skip-500mb", action="store_true", help="Skip 500MB dataset"
    )
    parser.add_argument(
        "--skip-1gb", action="store_true", help="Skip 1GB dataset"
    )
    parser.add_argument(
        "--custom-size", type=int, help="Generate custom dataset (number of rows)"
    )
    parser.add_argument(
        "--edges-per-source", type=int, default=10, help="Edges per source workload"
    )
    parser.add_argument(
        "--output", default="test/output/performance_results.json", help="Output file for metrics"
    )
    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.output).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics_list = []

    try:
        # Test 500MB dataset (~8-10M rows, ~60 bytes per row)
        if not args.skip_500mb:
            clear_table()
            metrics = load_data_to_clickhouse(
                num_rows=9_000_000,
                dataset_label="500MB Dataset",
                edges_per_source=args.edges_per_source,
            )
            metrics_list.append(metrics)

        # Test 1GB dataset (~16-20M rows)
        if not args.skip_1gb:
            clear_table()
            metrics = load_data_to_clickhouse(
                num_rows=18_000_000,
                dataset_label="1GB Dataset",
                edges_per_source=args.edges_per_source,
            )
            metrics_list.append(metrics)

        # Test custom size if specified
        if args.custom_size:
            clear_table()
            metrics = load_data_to_clickhouse(
                num_rows=args.custom_size,
                dataset_label=f"Custom Dataset ({args.custom_size:,} rows)",
                edges_per_source=args.edges_per_source,
            )
            metrics_list.append(metrics)

    except Exception as e:
        print(f"Error during testing: {e}", file=sys.stderr)
        return 1

    # Print summary and save metrics
    if metrics_list:
        print_summary(metrics_list)
        save_metrics(metrics_list, args.output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
