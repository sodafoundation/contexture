from mcp_tools import (
    list_databases_tool,
    list_tables_tool,
    describe_table_tool,
    execute_query_tool,
    get_table_stats_tool,
    get_db_stats_tool,
    get_slow_queries_tool,
    check_db_health_tool,
)

TOOLS = {
    "list_databases":   list_databases_tool,
    "list_tables":      list_tables_tool,
    "describe_table":   describe_table_tool,
    "execute_query":    execute_query_tool,
    "get_table_stats":  get_table_stats_tool,
    "get_db_stats":     get_db_stats_tool,
    "get_slow_queries": get_slow_queries_tool,
    "check_db_health":  check_db_health_tool,
}
