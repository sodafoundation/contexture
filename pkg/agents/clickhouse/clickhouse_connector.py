"""
ClickHouse connector for SODA Contexture.

Provides low-level query functions used by the MCP tools.
Connection settings are loaded from config/clickhouse_config.yaml.
"""

import os
import yaml
import clickhouse_driver
from typing import Any, Dict, List, Optional, Tuple


def _load_config() -> List[Dict]:
    """Load clickhouse_config.yaml from the repo config directory."""
    here = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(here, "..", "..", "..", "config", "clickhouse_config.yaml")
    config_path = os.path.normpath(config_path)

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"clickhouse_config.yaml not found at {config_path}")

    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f)

    return cfg.get("clickhouse_instances", [])


def _get_client(instance: Dict) -> clickhouse_driver.Client:
    """Open a clickhouse-driver Client for a given config instance."""
    return clickhouse_driver.Client(
        host=instance.get("host", "localhost"),
        port=instance.get("port", 9000),
        user=instance.get("username", "default"),
        password=instance.get("password", ""),
        database=instance.get("database", "default"),
        secure=instance.get("secure", False),
    )


# ── public helpers ────────────────────────────────────────────────────────────

def get_all_instances() -> List[Dict]:
    return _load_config()


def list_databases(instance: Dict) -> List[Dict]:
    client = _get_client(instance)
    try:
        rows = client.execute(
            "SELECT name, engine FROM system.databases ORDER BY name"
        )
        return [{"name": r[0], "engine": r[1]} for r in rows]
    finally:
        client.disconnect()


def list_tables(instance: Dict, database: str = "default") -> List[Dict]:
    client = _get_client(instance)
    try:
        rows = client.execute(
            "SELECT name, engine, total_rows, formatReadableSize(total_bytes) AS size "
            "FROM system.tables WHERE database = %(db)s ORDER BY name",
            {"db": database},
        )
        return [
            {"name": r[0], "engine": r[1], "total_rows": r[2], "size": r[3]}
            for r in rows
        ]
    finally:
        client.disconnect()


def describe_table(instance: Dict, database: str, table: str) -> Dict[str, Any]:
    client = _get_client(instance)
    try:
        col_rows = client.execute(f"DESCRIBE TABLE `{database}`.`{table}`")
        columns = [
            {
                "name": r[0],
                "type": r[1],
                "default_type": r[2],
                "default_expression": r[3],
                "comment": r[4],
            }
            for r in col_rows
        ]
        stats = client.execute(
            "SELECT total_rows, formatReadableSize(total_bytes) "
            "FROM system.tables WHERE database = %(db)s AND name = %(tbl)s",
            {"db": database, "tbl": table},
        )
        row_count = stats[0][0] if stats else None
        disk_size = stats[0][1] if stats else None
        return {
            "database": database,
            "table": table,
            "columns": columns,
            "total_rows": row_count,
            "disk_size": disk_size,
        }
    finally:
        client.disconnect()


def execute_query(instance: Dict, sql: str, limit: int = 100) -> Tuple[List[Dict], List[str]]:
    """Run a read-only SELECT query, returning (rows, column_names)."""
    normalized = sql.strip().upper()
    if not (normalized.startswith("SELECT") or normalized.startswith("WITH")):
        raise ValueError("Only SELECT / WITH queries are allowed via execute_query.")

    client = _get_client(instance)
    try:
        rows, columns_meta = client.execute(sql, with_column_types=True)
        col_names = [c[0] for c in columns_meta]
        result = [dict(zip(col_names, row)) for row in rows[:limit]]
        return result, col_names
    finally:
        client.disconnect()


def get_table_stats(instance: Dict, database: str, table: str) -> Optional[Dict]:
    """Return system.tables stats for a specific table."""
    client = _get_client(instance)
    try:
        rows = client.execute(
            """
            SELECT
                total_rows,
                total_bytes,
                formatReadableSize(total_bytes)             AS disk_size,
                formatReadableSize(data_uncompressed_bytes) AS uncompressed_size,
                engine,
                partition_key,
                sorting_key,
                primary_key
            FROM system.tables
            WHERE database = %(db)s AND name = %(tbl)s
            """,
            {"db": database, "tbl": table},
        )
        if not rows:
            return None
        r = rows[0]
        return {
            "total_rows": r[0],
            "total_bytes": r[1],
            "disk_size": r[2],
            "uncompressed_size": r[3],
            "engine": r[4],
            "partition_key": r[5],
            "sorting_key": r[6],
            "primary_key": r[7],
        }
    finally:
        client.disconnect()


def get_db_stats(instance: Dict) -> Dict[str, Any]:
    """Return database-level stats from system.databases + system.metrics."""
    client = _get_client(instance)
    try:
        db_rows = client.execute(
            "SELECT name, engine FROM system.databases ORDER BY name"
        )
        metric_rows = client.execute(
            "SELECT metric, value FROM system.metrics WHERE metric IN "
            "('Query', 'Connection', 'TCPConnection', 'HTTPConnection') ORDER BY metric"
        )
        return {
            "databases": [{"name": r[0], "engine": r[1]} for r in db_rows],
            "metrics": {r[0]: r[1] for r in metric_rows},
        }
    finally:
        client.disconnect()


def get_slow_queries(
    instance: Dict, min_duration_ms: float = 100.0, limit: int = 10
) -> List[Dict]:
    """Return top slow queries from system.query_log (last 24 hours)."""
    client = _get_client(instance)
    try:
        rows = client.execute(
            """
            SELECT
                left(query, 200)                         AS query_preview,
                count()                                  AS calls,
                round(avg(query_duration_ms), 2)         AS avg_duration_ms,
                round(max(query_duration_ms), 2)         AS max_duration_ms,
                sum(read_rows)                           AS total_rows_read,
                formatReadableSize(sum(read_bytes))      AS total_bytes_read
            FROM system.query_log
            WHERE type = 'QueryFinish'
              AND query_duration_ms >= %(min_ms)s
              AND event_time >= now() - INTERVAL 1 DAY
            GROUP BY query
            ORDER BY avg_duration_ms DESC
            LIMIT %(lim)s
            """,
            {"min_ms": min_duration_ms, "lim": limit},
        )
        return [
            {
                "query_preview": r[0],
                "calls": r[1],
                "avg_duration_ms": r[2],
                "max_duration_ms": r[3],
                "total_rows_read": r[4],
                "total_bytes_read": r[5],
            }
            for r in rows
        ]
    finally:
        client.disconnect()


def check_db_health(instance: Dict) -> Dict[str, Any]:
    """Quick health summary: version, uptime, connections, running queries."""
    client = _get_client(instance)
    try:
        version = client.execute("SELECT version()")[0][0]
        uptime_rows = client.execute(
            "SELECT value FROM system.metrics WHERE metric = 'Uptime'"
        )
        uptime_secs = uptime_rows[0][0] if uptime_rows else None
        conn_rows = client.execute(
            "SELECT value FROM system.metrics WHERE metric = 'TCPConnection'"
        )
        connections = conn_rows[0][0] if conn_rows else None
        running_rows = client.execute("SELECT count() FROM system.processes")
        running_queries = running_rows[0][0] if running_rows else 0
        return {
            "version": version,
            "uptime_seconds": uptime_secs,
            "tcp_connections": connections,
            "running_queries": running_queries,
        }
    finally:
        client.disconnect()
