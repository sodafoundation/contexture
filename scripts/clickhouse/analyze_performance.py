#!/usr/bin/env python3
"""
Analyze and visualize ClickHouse performance test results.
Generates performance reports in text and JSON format.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def load_metrics(metrics_file: str) -> dict:
    """Load metrics from JSON file."""
    with open(metrics_file) as f:
        return json.load(f)


def analyze_metrics(metrics_data: dict) -> str:
    """Generate detailed analysis of performance metrics."""
    tests = metrics_data.get("tests", [])
    timestamp = metrics_data.get("timestamp", "Unknown")

    analysis = []
    analysis.append("=" * 70)
    analysis.append("CLICKHOUSE PERFORMANCE ANALYSIS REPORT")
    analysis.append("=" * 70)
    analysis.append(f"Generated: {timestamp}\n")

    if not tests:
        return "\n".join(analysis) + "\nNo test data found."

    # Overall statistics
    analysis.append("DATASET STATISTICS")
    analysis.append("-" * 70)

    for i, test in enumerate(tests, 1):
        analysis.append(f"\nDataset {i}:")
        analysis.append(f"  Size:              {test['dataset_size_mb']:.2f} MB")
        analysis.append(f"  Total Rows:        {test['num_rows']:,}")
        analysis.append(f"  Load Time:         {test['load_time_seconds']:.2f} seconds")
        analysis.append(f"  Throughput:        {test['rows_per_second']:,.0f} rows/sec")
        analysis.append(f"  Actual Table Size: {test['table_size_mb']:.2f} MB")

    # Query performance analysis
    analysis.append("\n" + "=" * 70)
    analysis.append("QUERY PERFORMANCE ANALYSIS")
    analysis.append("-" * 70)

    for i, test in enumerate(tests, 1):
        analysis.append(f"\nDataset {i} Query Times:")
        query_times = test.get("query_times", {})

        if not query_times:
            analysis.append("  No query data available")
            continue

        # Sort by execution time
        sorted_queries = sorted(query_times.items(), key=lambda x: x[1], reverse=True)

        for query_name, query_time in sorted_queries:
            bar_length = int(query_time * 100)
            bar = "█" * min(bar_length, 50)
            analysis.append(f"  {query_name:20s}: {query_time:8.3f}s {bar}")

    # Performance metrics
    analysis.append("\n" + "=" * 70)
    analysis.append("PERFORMANCE METRICS")
    analysis.append("-" * 70)

    # Calculate throughput comparison
    if len(tests) == 2:
        test1, test2 = tests[0], tests[1]
        throughput_ratio = test2["rows_per_second"] / test1["rows_per_second"]
        load_time_ratio = test2["load_time_seconds"] / test1["load_time_seconds"]

        analysis.append(f"\nComparison (Dataset 2 vs Dataset 1):")
        analysis.append(f"  Throughput Ratio:  {throughput_ratio:.2f}x")
        analysis.append(f"  Load Time Ratio:   {load_time_ratio:.2f}x")
        analysis.append(f"  Rows Ratio:        {test2['num_rows'] / test1['num_rows']:.2f}x")
        analysis.append(f"  Size Ratio:        {test2['dataset_size_mb'] / test1['dataset_size_mb']:.2f}x")

    # Recommendations
    analysis.append("\n" + "=" * 70)
    analysis.append("RECOMMENDATIONS & INSIGHTS")
    analysis.append("-" * 70)

    for i, test in enumerate(tests, 1):
        throughput = test["rows_per_second"]
        analysis.append(f"\nDataset {i}:")

        if throughput > 500_000:
            analysis.append("  ✓ Excellent throughput (>500K rows/sec)")
        elif throughput > 100_000:
            analysis.append("  ✓ Good throughput (100K-500K rows/sec)")
        else:
            analysis.append("  ⚠ Consider optimizing - throughput below 100K rows/sec")

        # Query time recommendations
        query_times = test.get("query_times", {})
        avg_query_time = sum(query_times.values()) / len(query_times) if query_times else 0

        if avg_query_time < 0.5:
            analysis.append("  ✓ Fast query performance (<500ms avg)")
        elif avg_query_time < 2.0:
            analysis.append("  ✓ Acceptable query performance (500ms-2s avg)")
        else:
            analysis.append("  ⚠ Consider adding indexes for slower queries")

        # Compression analysis
        compression_ratio = test["num_rows"] / test["table_size_mb"] if test["table_size_mb"] > 0 else 0
        analysis.append(f"  Compression:       {compression_ratio:,.0f} rows/MB")

    return "\n".join(analysis)


def generate_html_report(metrics_file: str, output_file: str) -> None:
    """Generate an HTML report with charts."""
    with open(metrics_file) as f:
        metrics_data = json.load(f)

    tests = metrics_data.get("tests", [])
    timestamp = metrics_data.get("timestamp", datetime.now().isoformat())

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>ClickHouse Performance Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #ff9500;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #555;
            margin-top: 30px;
            border-left: 4px solid #ff9500;
            padding-left: 10px;
        }}
        .chart-container {{
            background: white;
            padding: 20px;
            margin: 20px 0;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            margin: 20px 0;
            border-radius: 5px;
            overflow: hidden;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #ff9500;
            color: white;
            font-weight: bold;
        }}
        tr:hover {{
            background-color: #f9f9f9;
        }}
        .metric {{
            display: inline-block;
            background: white;
            padding: 20px;
            margin: 10px;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            min-width: 200px;
        }}
        .metric-value {{
            font-size: 24px;
            font-weight: bold;
            color: #ff9500;
        }}
        .metric-label {{
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
            margin-top: 5px;
        }}
    </style>
</head>
<body>
    <h1>ClickHouse Performance Report</h1>
    <p>Generated: {timestamp}</p>

    <h2>Dataset Summary</h2>
    <div id="metrics">
"""

    # Add metrics
    for i, test in enumerate(tests, 1):
        html_content += f"""    <div class="metric">
            <div class="metric-value">{test['dataset_size_mb']:.2f} MB</div>
            <div class="metric-label">Dataset {i} Size</div>
        </div>
        <div class="metric">
            <div class="metric-value">{test['num_rows']:,}</div>
            <div class="metric-label">Total Rows</div>
        </div>
        <div class="metric">
            <div class="metric-value">{test['rows_per_second']:,.0f}</div>
            <div class="metric-label">Load Throughput (rows/sec)</div>
        </div>
"""

    html_content += """    </div>

    <h2>Load Performance</h2>
    <div class="chart-container">
        <canvas id="loadChart"></canvas>
    </div>

    <h2>Query Performance</h2>
    <div class="chart-container">
        <canvas id="queryChart"></canvas>
    </div>

    <h2>Detailed Results</h2>
    <table>
        <tr>
            <th>Dataset</th>
            <th>Size (MB)</th>
            <th>Rows</th>
            <th>Load Time (s)</th>
            <th>Throughput (rows/s)</th>
        </tr>
"""

    for i, test in enumerate(tests, 1):
        html_content += f"""        <tr>
            <td>Dataset {i}</td>
            <td>{test['dataset_size_mb']:.2f}</td>
            <td>{test['num_rows']:,}</td>
            <td>{test['load_time_seconds']:.2f}</td>
            <td>{test['rows_per_second']:,.0f}</td>
        </tr>
"""

    html_content += """    </table>

    <script>
"""

    # Add charts data
    dataset_labels = [f"Dataset {i}" for i in range(1, len(tests) + 1)]
    load_times = [test["load_time_seconds"] for test in tests]
    throughputs = [test["rows_per_second"] / 1000 for test in tests]  # in thousands

    html_content += f"""
        // Load Performance Chart
        var ctx = document.getElementById('loadChart').getContext('2d');
        var loadChart = new Chart(ctx, {{
            type: 'bar',
            data: {{
                labels: {json.dumps(dataset_labels)},
                datasets: [
                    {{
                        label: 'Load Time (seconds)',
                        data: {json.dumps(load_times)},
                        backgroundColor: 'rgba(255, 149, 0, 0.7)',
                        borderColor: 'rgba(255, 149, 0, 1)',
                        borderWidth: 1
                    }},
                    {{
                        label: 'Throughput (K rows/sec)',
                        data: {json.dumps(throughputs)},
                        backgroundColor: 'rgba(100, 200, 255, 0.7)',
                        borderColor: 'rgba(100, 200, 255, 1)',
                        borderWidth: 1
                    }}
                ]
            }},
            options: {{
                responsive: true,
                scales: {{
                    y: {{
                        beginAtZero: true
                    }}
                }}
            }}
        }});

        // Query Performance Chart
        var ctx2 = document.getElementById('queryChart').getContext('2d');
"""

    # Add query chart
    if tests and tests[0].get("query_times"):
        query_names = list(tests[0]["query_times"].keys())
        query_data_sets = []

        for i, test in enumerate(tests):
            query_times = test.get("query_times", {})
            times = [query_times.get(name, 0) for name in query_names]
            query_data_sets.append({
                "label": f"Dataset {i + 1}",
                "data": times,
                "borderColor": f"rgba({100 + i * 50}, {150 + i * 30}, {200 - i * 50}, 1)",
                "backgroundColor": f"rgba({100 + i * 50}, {150 + i * 30}, {200 - i * 50}, 0.1)",
                "borderWidth": 2
            })

        html_content += f"""
        var queryChart = new Chart(ctx2, {{
            type: 'line',
            data: {{
                labels: {json.dumps(query_names)},
                datasets: {json.dumps(query_data_sets)}
            }},
            options: {{
                responsive: true,
                scales: {{
                    y: {{
                        beginAtZero: true
                    }}
                }}
            }}
        }});
"""

    html_content += """
    </script>
</body>
</html>
"""

    with open(output_file, "w") as f:
        f.write(html_content)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze ClickHouse performance test results")
    parser.add_argument(
        "--input", default="test/output/performance_results.json",
        help="Input metrics JSON file"
    )
    parser.add_argument(
        "--output", default="test/output/performance_report.txt",
        help="Output report file (text)"
    )
    parser.add_argument(
        "--html", default="test/output/performance_report.html",
        help="Output report file (HTML)"
    )
    args = parser.parse_args()

    # Check if input file exists
    if not Path(args.input).exists():
        print(f"Error: Input file not found: {args.input}")
        return 1

    # Load and analyze metrics
    metrics_data = load_metrics(args.input)
    analysis = analyze_metrics(metrics_data)

    # Print to console
    print(analysis)

    # Save text report
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        f.write(analysis)
    print(f"\n✓ Text report saved to {args.output}")

    # Generate HTML report
    try:
        generate_html_report(args.input, args.html)
        print(f"✓ HTML report saved to {args.html}")
    except Exception as e:
        print(f"Warning: Could not generate HTML report: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
