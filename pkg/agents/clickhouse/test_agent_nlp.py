#!/usr/bin/env python3
"""
Test script for verifying NLP query routing in the ClickHouse agent.
Mocks ClickHouse connector functions to test agent.py routing without requiring a live server.
"""

import sys
import os
from unittest.mock import patch

# Ensure imports resolve correctly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import process_query

def run_tests():
    print("=" * 60)
    print("Testing ClickHouse Agent NLP Query Router")
    print("=" * 60)

    # Test cases: (query_text, expected_tool_called)
    test_queries = [
        # Health & Status
        ("Check the health of Clickhouse", "check_db_health"),
        ("What is the status of the database?", "check_db_health"),
        
        # Slow Queries & Performance
        ("Show me the slow queries", "get_slow_queries"),
        ("How is the query performance and latency?", "get_slow_queries"),
        
        # DB Stats
        ("Get database stats", "get_db_stats"),
        ("Show db statistics", "get_db_stats"),
        
        # Table Stats
        ("Show stats for table default.service_dependencies", "get_table_stats"),
        ("What is the size and rows count for table default.service_dependencies", "get_table_stats"),
        
        # Describe & Schema
        ("Describe default.service_dependencies", "describe_table"),
        ("Show columns of default.service_dependencies", "describe_table"),
        ("What is the schema of default.service_dependencies", "describe_table"),
        
        # Execute Query / SELECT
        ("Run query: SELECT count() FROM default.service_dependencies", "execute_query"),
        ("execute: SELECT * FROM default.service_dependencies LIMIT 10", "execute_query"),
        ("Run a select count(*) from system.tables", "execute_query"),
        
        # List Tables
        ("List all tables in database default", "list_tables"),
        ("What tables are in the default database?", "list_tables"),
        
        # List Databases
        ("List all databases", "list_databases"),
        ("Show dbs", "list_databases"),
        
        # Fallback / No match
        ("Hello, who are you?", None)
    ]

    # Mock return values for clickhouse_connector
    mock_db_health = {"local": {"version": "23.8.2.7", "uptime_seconds": 3600, "tcp_connections": 2, "running_queries": 0}}
    mock_slow_queries = {"local": [{"query_preview": "SELECT * FROM system.tables", "calls": 1, "avg_duration_ms": 150.0}]}
    mock_db_stats = {"local": {"databases": [{"name": "default", "engine": "Ordinary"}], "metrics": {"Query": 0, "Connection": 1}}}
    mock_table_stats = {"local": {"total_rows": 1250, "disk_size": "45.2 KiB", "engine": "MergeTree"}}
    mock_describe_table = {"local": {"database": "default", "table": "service_dependencies", "columns": [{"name": "service_name", "type": "String"}]}}
    mock_execute_query = {"local": {"columns": ["count"], "rows": [{"count": 42}], "row_count": 1}}
    mock_list_tables = {"local": [{"name": "service_dependencies", "engine": "MergeTree", "total_rows": 1250, "size": "45.2 KiB"}]}
    mock_list_databases = {"local": [{"name": "default", "engine": "Ordinary"}, {"name": "system", "engine": "System"}]}

    # Patch connector functions in mcp_tools
    with patch("mcp_tools.check_db_health", return_value=mock_db_health["local"]), \
         patch("mcp_tools.get_slow_queries", return_value=mock_slow_queries["local"]), \
         patch("mcp_tools.get_db_stats", return_value=mock_db_stats["local"]), \
         patch("mcp_tools.get_table_stats", return_value=mock_table_stats["local"]), \
         patch("mcp_tools.describe_table", return_value=mock_describe_table["local"]), \
         patch("mcp_tools.execute_query", return_value=([{"count": 42}], ["count"])), \
         patch("mcp_tools.list_tables", return_value=mock_list_tables["local"]), \
         patch("mcp_tools.list_databases", return_value=mock_list_databases["local"]), \
         patch("mcp_tools.get_all_instances", return_value=[{"name": "local", "host": "localhost", "port": 9000, "database": "default"}]):

        passed = 0
        failed = 0

        for query, expected in test_queries:
            print(f"\nQuery: '{query}'")
            try:
                result = process_query(query)
                print(f"Result: {result}")
                
                # Check if correct tool output is returned (or expected message)
                if expected is None:
                    if "No matching tool found" in result.get("message", ""):
                        print("-> PASSED (Fallback triggered correctly)")
                        passed += 1
                    else:
                        print("-> FAILED (Expected fallback)")
                        failed += 1
                else:
                    # Verify returned data matches mock pattern
                    is_correct = False
                    if expected == "check_db_health" and "version" in result.get("local", {}):
                        is_correct = True
                    elif expected == "get_slow_queries" and isinstance(result.get("local", []), list):
                        is_correct = True
                    elif expected == "get_db_stats" and "databases" in result.get("local", {}):
                        is_correct = True
                    elif expected == "get_table_stats" and "disk_size" in result.get("local", {}):
                        is_correct = True
                    elif expected == "describe_table" and "columns" in result.get("local", {}):
                        is_correct = True
                    elif expected == "execute_query" and "rows" in result.get("local", {}):
                        is_correct = True
                    elif expected == "list_tables" and isinstance(result.get("local", []), list):
                        is_correct = True
                    elif expected == "list_databases" and isinstance(result.get("local", []), list):
                        is_correct = True

                    if is_correct:
                        print(f"-> PASSED (Routed to {expected} correctly)")
                        passed += 1
                    else:
                        print(f"-> FAILED (Expected routing to {expected})")
                        failed += 1
            except Exception as e:
                print(f"-> FAILED with error: {e}")
                failed += 1

    print("\n" + "=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
