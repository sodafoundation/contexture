# server.py — ClickHouse MCP Server for SODA Contexture
#
# Implements the same FastMCP @app.tool() pattern as pkg/agents/postgres/server.py.
# Connects to ClickHouse instances defined in config/clickhouse_config.yaml.
#
# Run (always from the pkg/agents/clickhouse/ directory):
#   python server.py                         # stdio transport (default)
#   python server.py --transport sse         # SSE/HTTP on port 8004
#   python server.py --transport sse --port 9000  # custom port

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP
from clickhouse_connector import (
    get_all_instances,
    list_databases,
    list_tables,
    describe_table,
    execute_query,
    get_table_stats,
    get_db_stats,
    get_slow_queries,
    check_db_health,
)

app = FastMCP("ClickHouse MCP Server")

# ── lazy-load instances ───────────────────────────────────────────────────────

def _instances() -> List[Dict]:
    try:
        return get_all_instances()
    except FileNotFoundError as e:
        print(f"[clickhouse-mcp] WARNING: {e}")
        return []


# ── tools ─────────────────────────────────────────────────────────────────────

@app.tool()
def ch_list_databases() -> Dict[str, Any]:
    """
    List all databases in ClickHouse across configured instances.
    Returns name and engine for each database.
    Useful for understanding what databases exist before querying.
    """
    all_results = {}
    for inst in _instances():
        name = inst.get("name", "default")
        try:
            all_results[name] = list_databases(inst)
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "databases_per_instance": all_results,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def ch_list_tables(database: str = "default") -> Dict[str, Any]:
    """
    List all tables in the given ClickHouse database.
    Returns table name, engine, total rows, and disk size.

    Args:
        database: Database name to query (default: 'default').
    """
    all_results = {}
    for inst in _instances():
        name = inst.get("name", "default")
        try:
            all_results[name] = list_tables(inst, database)
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "database": database,
        "tables_per_instance": all_results,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def ch_describe_table(database: str, table: str) -> Dict[str, Any]:
    """
    Return the full structure of a ClickHouse table: columns (name, type, defaults),
    total row count, and disk size. Essential for understanding data shape before querying.

    Args:
        database: Database name (e.g. 'default').
        table:    Table name.
    """
    all_results = {}
    for inst in _instances():
        name = inst.get("name", "default")
        try:
            all_results[name] = describe_table(inst, database, table)
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "description_per_instance": all_results,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def ch_execute_query(sql: str, limit: int = 100) -> Dict[str, Any]:
    """
    Execute a read-only SELECT (or WITH) query against ClickHouse and return results.
    Non-SELECT statements are rejected.

    Args:
        sql:   A SELECT or WITH SQL query.
        limit: Maximum number of rows to return (default: 100).
    """
    all_results = {}
    for inst in _instances():
        name = inst.get("name", "default")
        try:
            rows, cols = execute_query(inst, sql, limit)
            all_results[name] = {
                "columns":   cols,
                "rows":      rows,
                "row_count": len(rows),
            }
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "query":                  sql,
        "results_per_instance":   all_results,
        "timestamp":              datetime.now().isoformat(),
    }


@app.tool()
def ch_get_table_stats(database: str, table: str) -> Dict[str, Any]:
    """
    Return storage statistics for a ClickHouse table from system.tables:
    total rows, disk size, uncompressed size, engine, partition/sorting/primary keys.

    Args:
        database: Database name.
        table:    Table name.
    """
    all_results = {}
    for inst in _instances():
        name = inst.get("name", "default")
        try:
            stats = get_table_stats(inst, database, table)
            all_results[name] = (
                stats if stats
                else {"error": f"Table {database}.{table} not found in system.tables"}
            )
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "database":           database,
        "table":              table,
        "stats_per_instance": all_results,
        "timestamp":          datetime.now().isoformat(),
    }


@app.tool()
def ch_get_db_stats() -> Dict[str, Any]:
    """
    Return database-level statistics: list of databases with engines,
    and live system metrics (active queries, TCP connections, etc.).
    Provides a quick operational snapshot of the ClickHouse server.
    """
    all_results = {}
    for inst in _instances():
        name = inst.get("name", "default")
        try:
            all_results[name] = get_db_stats(inst)
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "db_stats_per_instance": all_results,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def ch_get_slow_queries(
    min_duration_ms: float = 100.0,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Return the top slow queries from system.query_log (last 24 hours).
    Shows query preview, call count, avg/max duration, rows and bytes read.
    Use this to identify performance hotspots.

    Args:
        min_duration_ms: Minimum average execution time in ms (default: 100).
        limit:           Maximum number of queries to return (default: 10).
    """
    all_results = {}
    for inst in _instances():
        name = inst.get("name", "default")
        try:
            all_results[name] = get_slow_queries(inst, min_duration_ms, limit)
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "min_duration_ms":           min_duration_ms,
        "slow_queries_per_instance": all_results,
        "timestamp":                 datetime.now().isoformat(),
    }


@app.tool()
def ch_check_db_health() -> Dict[str, Any]:
    """
    Return a health summary for each configured ClickHouse instance:
    version, uptime in seconds, TCP connections, and number of running queries.
    Use this as the first tool to call when diagnosing database issues.
    """
    all_results = {}
    for inst in _instances():
        name = inst.get("name", "default")
        try:
            all_results[name] = check_db_health(inst)
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "health_per_instance": all_results,
        "timestamp": datetime.now().isoformat(),
    }


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ClickHouse MCP Server for SODA Contexture")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport type (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8004,
        help="Port for SSE transport (default: 8004)",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        app.run(transport="sse", port=args.port)
    else:
        app.run()
