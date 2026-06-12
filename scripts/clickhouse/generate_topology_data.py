#!/usr/bin/env python3
"""Generate synthetic ClickHouse topology rows for service_dependencies."""

from __future__ import annotations

import argparse
import csv
import datetime
import random
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic service dependency rows for ClickHouse.",
    )
    parser.add_argument(
        "--num-sources",
        type=int,
        default=1000,
        help="Number of unique source workloads to generate.",
    )
    parser.add_argument(
        "--edges-per-source",
        type=int,
        default=10,
        help="Number of outgoing edges for each source workload.",
    )
    parser.add_argument(
        "--start-time",
        type=str,
        default=None,
        help="Start timestamp for event_time rows (UTC, e.g. '2026-06-10 00:00:00'). Defaults to now - 1 hour.",
    )
    parser.add_argument(
        "--duration-minutes",
        type=int,
        default=60,
        help="Spread event_time values across this many past minutes.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible edge generation.",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="service",
        help="Prefix to use for generated service names.",
    )
    return parser.parse_args()


def build_workloads(prefix: str, count: int) -> list[str]:
    return [f"{prefix}-{i:05d}" for i in range(1, count + 1)]


def parse_start_time(value: str | None) -> datetime.datetime:
    if value is None:
        return datetime.datetime.utcnow() - datetime.timedelta(hours=1)

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(value, fmt)
        except ValueError:
            continue

    raise ValueError(
        "Invalid start-time format. Use 'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DDTHH:MM:SS', or 'YYYY-MM-DD'."
    )


def generate_rows(
    sources: list[str],
    edges_per_source: int,
    start_time: datetime.datetime,
    duration_minutes: int,
) -> None:
    total = len(sources)
    writer = csv.writer(sys.stdout, lineterminator="\n")

    for index, source in enumerate(sources, start=1):
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


def main() -> int:
    args = parse_args()
    random.seed(args.seed)

    sources = build_workloads(args.prefix, args.num_sources)
    start_time = parse_start_time(args.start_time)

    generate_rows(
        sources=sources,
        edges_per_source=args.edges_per_source,
        start_time=start_time,
        duration_minutes=args.duration_minutes,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
