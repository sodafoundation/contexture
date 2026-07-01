#!/usr/bin/env python3
"""
Quick connectivity test for the ClickHouse MCP agent.

Run from this directory:
    cd pkg/agents/clickhouse
    python test_connection.py

Reads connection settings from config/clickhouse_config.yaml.
Verifies that:
  1. The config file is found and parses correctly.
  2. Each configured instance accepts a connection.
  3. list_databases() and list_tables() return data without errors.
"""
import sys
import os

# Ensure imports resolve regardless of working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from clickhouse_connector import get_all_instances, _get_client, list_databases, list_tables


def _hr():
    print("-" * 50)


def main():
    # ── 1. Config loading ────────────────────────────────
    print("Loading clickhouse_config.yaml...")
    try:
        instances = get_all_instances()
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        print(
            "\nMake sure config/clickhouse_config.yaml exists at the repo root.\n"
        )
        sys.exit(1)

    if not instances:
        print("ERROR: No instances found in clickhouse_config.yaml. Add at least one entry under clickhouse_instances:")
        sys.exit(1)

    print(f"Found {len(instances)} instance(s): {[i.get('name') for i in instances]}\n")

    # ── 2. Per-instance checks ───────────────────────────
    all_ok = True
    for inst in instances:
        name = inst.get("name", "default")
        _hr()
        print(f"Instance : {name}")
        print(f"Host     : {inst.get('host')}:{inst.get('port', 9000)}")
        print(f"Database : {inst.get('database')}")
        print(f"User     : {inst.get('username')}")

        # Connection test
        try:
            client = _get_client(inst)
            client.execute("SELECT 1")
            client.disconnect()
            print("Connection: OK")
        except Exception as exc:
            print(f"Connection: FAILED — {exc}")
            all_ok = False
            continue

        # list_databases
        try:
            dbs = list_databases(inst)
            print(f"Databases ({len(dbs)}):")
            for db in dbs:
                print(f"  - {db['name']}  [{db['engine']}]")
        except Exception as exc:
            print(f"list_databases: FAILED — {exc}")
            all_ok = False

        # list_tables
        try:
            tables = list_tables(inst, inst.get("database", "default"))
            print(f"Tables in '{inst.get('database', 'default')}' ({len(tables)}):")
            for t in tables[:5]:
                print(f"  - {t['name']}  [{t['engine']}]  rows={t['total_rows']}  size={t['size']}")
            if len(tables) > 5:
                print(f"  ... and {len(tables) - 5} more")
        except Exception as exc:
            print(f"list_tables: FAILED — {exc}")
            all_ok = False

    # ── 3. Summary ───────────────────────────────────────
    _hr()
    if all_ok:
        print("All instances OK.")
        sys.exit(0)
    else:
        print("One or more instances had errors (see above).")
        sys.exit(1)


if __name__ == "__main__":
    main()
