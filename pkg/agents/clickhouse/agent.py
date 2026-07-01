"""
Natural-language query router for the ClickHouse agent.

Maps simple keyword patterns to tool calls — mirrors postgres/agent.py.
For richer NL→workflow routing, the main client_dynamic.py / client_dynamic_ui.py
pipeline is used instead (it talks to the FastMCP server directly via Ollama).
"""

from tool_registry import TOOLS


def process_query(query: str) -> dict:
    q = query.lower()

    if "health" in q or "status" in q:
        return TOOLS["check_db_health"]()

    if "slow" in q or "performance" in q or "latency" in q:
        return TOOLS["get_slow_queries"]()

    if "stat" in q and ("db" in q or "database" in q):
        return TOOLS["get_db_stats"]()

    if ("stat" in q or "size" in q or "row" in q) and "table" in q:
        # expect "stats for table <database>.<table>" or similar
        parts = q.split()
        database, table = "default", ""
        for i, p in enumerate(parts):
            if "." in p:
                database, table = p.split(".", 1)
            elif p == "table" and i + 1 < len(parts):
                table = parts[i + 1]
        if table:
            return TOOLS["get_table_stats"](database=database, table=table)
        return {"message": "Please specify table name, e.g. 'stats for table default.service_dependencies'"}

    if "describe" in q or "columns" in q or "schema of" in q:
        parts = q.split()
        database, table = "default", ""
        for p in parts:
            if "." in p:
                database, table = p.split(".", 1)
        if table:
            return TOOLS["describe_table"](database=database, table=table)
        return {"message": "Please specify table, e.g. 'describe default.service_dependencies'"}

    if "select" in q or "query" in q:
        sql = query
        for prefix in ["query:", "run:", "execute:"]:
            if prefix in q:
                sql = query[q.index(prefix) + len(prefix):].strip()
                break
        return TOOLS["execute_query"](sql=sql)

    if "table" in q:
        database = "default"
        parts = q.split()
        for i, p in enumerate(parts):
            if p in ("database", "in") and i + 1 < len(parts):
                database = parts[i + 1]
        return TOOLS["list_tables"](database=database)

    if "database" in q or "db" in q:
        return TOOLS["list_databases"]()

    return {"message": "No matching tool found. Try asking about databases, tables, health, slow queries, or run a SELECT."}
