"""
MCP tool wrapper functions for the ClickHouse agent.

Each function corresponds to one @app.tool() in server.py.
Separated here so they can be called directly (e.g. from agent.py or tests)
without starting the full FastMCP server.
"""

from typing import Any, Dict, List, Optional
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


def _instances():
    return get_all_instances()


# ── tools ─────────────────────────────────────────────────────────────────────

def list_databases_tool() -> Dict[str, Any]:
    results = {}
    for inst in _instances():
        try:
            results[inst["name"]] = list_databases(inst)
        except Exception as e:
            results[inst["name"]] = {"error": str(e)}
    return results


def list_tables_tool(database: str = "default") -> Dict[str, Any]:
    results = {}
    for inst in _instances():
        try:
            results[inst["name"]] = list_tables(inst, database)
        except Exception as e:
            results[inst["name"]] = {"error": str(e)}
    return results


def describe_table_tool(database: str, table: str) -> Dict[str, Any]:
    results = {}
    for inst in _instances():
        try:
            results[inst["name"]] = describe_table(inst, database, table)
        except Exception as e:
            results[inst["name"]] = {"error": str(e)}
    return results


def execute_query_tool(sql: str, limit: int = 100) -> Dict[str, Any]:
    results = {}
    for inst in _instances():
        try:
            rows, cols = execute_query(inst, sql, limit)
            results[inst["name"]] = {"columns": cols, "rows": rows, "row_count": len(rows)}
        except Exception as e:
            results[inst["name"]] = {"error": str(e)}
    return results


def get_table_stats_tool(database: str, table: str) -> Dict[str, Any]:
    results = {}
    for inst in _instances():
        try:
            stats = get_table_stats(inst, database, table)
            results[inst["name"]] = stats if stats else {
                "error": f"Table {database}.{table} not found in system.tables"
            }
        except Exception as e:
            results[inst["name"]] = {"error": str(e)}
    return results


def get_db_stats_tool() -> Dict[str, Any]:
    results = {}
    for inst in _instances():
        try:
            results[inst["name"]] = get_db_stats(inst)
        except Exception as e:
            results[inst["name"]] = {"error": str(e)}
    return results


def get_slow_queries_tool(min_duration_ms: float = 100.0, limit: int = 10) -> Dict[str, Any]:
    results = {}
    for inst in _instances():
        try:
            results[inst["name"]] = get_slow_queries(inst, min_duration_ms, limit)
        except Exception as e:
            results[inst["name"]] = {"error": str(e)}
    return results


def check_db_health_tool() -> Dict[str, Any]:
    results = {}
    for inst in _instances():
        try:
            results[inst["name"]] = check_db_health(inst)
        except Exception as e:
            results[inst["name"]] = {"error": str(e)}
    return results
