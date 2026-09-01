#!/usr/bin/env python3
"""
ClickHouse NL Chatbot — Terminal-based natural language query interface.

Routes ALL queries through the ClickHouse MCP Server (port 8004)
using FastMCP Client. No direct ClickHouse connection.

Usage:
    1. Start the MCP server:  .\run.bat up
    2. Run chatbot:           python scripts/clickhouse/chatbot.py
"""

import os
import sys
import yaml
import httpx
import json
import re
import asyncio
from fastmcp import Client
from tabulate import tabulate

# ── colours ───────────────────────────────────────────────────────────────────
CYAN    = "\033[96m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
RESET   = "\033[0m"

# ── config ────────────────────────────────────────────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(HERE, "..", "..", "config")

def _load_yaml(name):
    path = os.path.normpath(os.path.join(CONFIG_DIR, name))
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}

ollama_cfg  = _load_yaml("ollama_config.yaml")
server_cfg  = _load_yaml("mcp_server_config.yaml")

OLLAMA_URL   = ollama_cfg.get("ollama_url", "http://localhost:11434")
OLLAMA_MODEL = ollama_cfg.get("ollama_model", "qwen2.5-coder:14b")

# ── MCP Client (connects to ClickHouse MCP Server) ───────────────────────────
MCP_URL = server_cfg.get("clickhouse_mcp_url", "http://localhost:8004/sse")
# Normalize: if config says /mcp, replace with /sse for FastMCP SSE transport
if MCP_URL.endswith("/mcp"):
    MCP_URL = MCP_URL.rsplit("/mcp", 1)[0] + "/sse"
mcp_client = Client(MCP_URL)

# ── schema context for LLM ───────────────────────────────────────────────────
SCHEMA_CONTEXT = """
Database: ecommerce  (MySQL, InnoDB engine)

Tables:
1. ecommerce.customers
   - customer_id  UInt32  (PRIMARY KEY)
   - name         String
   - email        String
   - city         String

2. ecommerce.products
   - product_id   UInt32  (PRIMARY KEY)
   - name         String
   - category     String
   - price        Float64
   - stock        UInt32

3. ecommerce.orders
   - order_id     UInt32  (PRIMARY KEY)
   - customer_id  UInt32  (FK -> customers.customer_id)
   - product_id   UInt32  (FK -> products.product_id)
   - quantity     UInt32
   - order_date   Date

Relationships:
  customers -> orders   via customer_id
  orders    -> products via product_id
"""


# ── offline NL -> SQL (keyword-based fallback) ────────────────────────────────
def _offline_nl_to_sql(q):
    """Convert common natural language patterns to SQL without an LLM."""
    ql = q.lower()

    # Normalize common typos / misspellings
    typo_map = {
        "coustmer": "customer", "coustomer": "customer", "custmer": "customer",
        "cusotmer": "customer", "cutomer": "customer", "costumer": "customer",
        "producr": "product", "prodcut": "product", "pruduct": "product",
        "revanue": "revenue", "revnue": "revenue",
        "atleast": "at least", "atmost": "at most",
        "ordrs": "orders", "ordr": "order",
        "totel": "total", "totol": "total",
        "averge": "average", "avrage": "average",
        "spendig": "spending", "speding": "spending",
    }
    for typo, fix in typo_map.items():
        ql = ql.replace(typo, fix)

    # "list all customers" / "show customers"
    if re.search(r"(list|show|all)\b.*\bcustomer", ql) and not re.search(r"order|buy|product|spend", ql):
        return "SELECT * FROM ecommerce.customers ORDER BY customer_id;"

    # "customers with at least N orders"
    m = re.search(r"customer.*(?:at\s*least|more\s*than|>=?)\s*(\d+)\s*order", ql)
    if m:
        n = int(m.group(1))
        return (
            "SELECT c.name, c.email, c.city, count(*) AS order_count "
            "FROM ecommerce.orders o "
            "INNER JOIN ecommerce.customers c ON o.customer_id = c.customer_id "
            "GROUP BY c.name, c.email, c.city "
            "HAVING order_count >= " + str(n) + " "
            "ORDER BY order_count DESC;"
        )

    # "list all orders" / "show orders" / "show all orders"
    if re.search(r"(list|show|all)\b.*\border", ql) and not re.search(r"customer.*order|at\s*least|more\s*than", ql):
        return (
            "SELECT o.order_id, c.name AS customer, p.name AS product, "
            "o.quantity, p.price, (o.quantity * p.price) AS total, o.order_date "
            "FROM ecommerce.orders o "
            "INNER JOIN ecommerce.customers c ON o.customer_id = c.customer_id "
            "INNER JOIN ecommerce.products p ON o.product_id = p.product_id "
            "ORDER BY o.order_date;"
        )

    # "what products did X buy" / "X bought what"
    m = re.search(r"(?:what|which)\s+product.*\b(\w+)\s+(?:buy|bought|order|purchase)", ql)
    if not m:
        _skip = r"(?!most|least|average|avg|total|many|all|any|each|every|per|the|this|no)\b"
        m = re.search(r"(" + _skip + r"\w+)\s+(?:bought|purchased)", ql)
    if m:
        name = m.group(1).capitalize()
        return (
            "SELECT c.name AS customer, p.name AS product, p.category, "
            "o.quantity AS qty, o.order_date "
            "FROM ecommerce.orders o "
            "INNER JOIN ecommerce.customers c ON o.customer_id = c.customer_id "
            "INNER JOIN ecommerce.products p ON o.product_id = p.product_id "
            "WHERE c.name = '" + name + "' "
            "ORDER BY o.order_date;"
        )

    # "total revenue per category" / "revenue by category"
    if re.search(r"revenue.*categor|categor.*revenue|sales.*categor", ql):
        return (
            "SELECT p.category, sum(o.quantity * p.price) AS total_revenue "
            "FROM ecommerce.orders o "
            "INNER JOIN ecommerce.products p ON o.product_id = p.product_id "
            "GROUP BY p.category ORDER BY total_revenue DESC;"
        )

    # "top N customers by spending"
    m = re.search(r"top\s*(\d+)?\s*customer.*(?:spend|revenue|amount)", ql)
    if m:
        n = int(m.group(1)) if m.group(1) else 5
        return (
            "SELECT c.name, sum(o.quantity * p.price) AS total_spent "
            "FROM ecommerce.orders o "
            "INNER JOIN ecommerce.customers c ON o.customer_id = c.customer_id "
            "INNER JOIN ecommerce.products p ON o.product_id = p.product_id "
            "GROUP BY c.name ORDER BY total_spent DESC LIMIT " + str(n) + ";"
        )

    # "which city has the most orders"
    if re.search(r"city.*(?:most|max).*order|order.*(?:per|by)\s*city", ql):
        return (
            "SELECT c.city, count(*) AS order_count "
            "FROM ecommerce.orders o "
            "INNER JOIN ecommerce.customers c ON o.customer_id = c.customer_id "
            "GROUP BY c.city ORDER BY order_count DESC;"
        )

    # "average order value" / "avg order"
    if re.search(r"averag|avg.*order|order.*avg", ql):
        return (
            "SELECT c.name, avg(o.quantity * p.price) AS avg_order_value "
            "FROM ecommerce.orders o "
            "INNER JOIN ecommerce.customers c ON o.customer_id = c.customer_id "
            "INNER JOIN ecommerce.products p ON o.product_id = p.product_id "
            "GROUP BY c.name ORDER BY avg_order_value DESC;"
        )

    # "list all products" / "show products"
    if re.search(r"(list|show|all)\b.*\bproduct", ql):
        return "SELECT * FROM ecommerce.products ORDER BY product_id;"

    # "total orders" / "how many orders"
    if re.search(r"total.*order|how\s*many.*order|count.*order", ql):
        return "SELECT count(*) AS total_orders FROM ecommerce.orders;"

    return ""


# ── NL -> SQL via Ollama (with offline fallback) ─────────────────────────────
def nl_to_sql(question):
    """Try Ollama first; if unreachable, fall back to keyword-based conversion."""
    prompt = (
        "You are a ClickHouse SQL expert. Given the database schema below, "
        "convert the user's natural language question into a single valid "
        "ClickHouse SELECT query.\n\n"
        "Rules:\n"
        "- Return ONLY the SQL query, nothing else. No explanation.\n"
        "- Always use fully qualified table names (e.g. ecommerce.customers).\n"
        "- Use INNER JOIN for relationships.\n"
        "- Use ClickHouse-compatible syntax (COUNT(), etc.).\n"
        "- For aggregations, use appropriate GROUP BY and HAVING.\n"
        "- Do NOT wrap the query in backticks or markdown.\n\n"
        + "Schema:\n" + SCHEMA_CONTEXT + "\n\n"
        + "Question: " + question + "\n\n"
        "SQL:"
    )

    try:
        resp = httpx.post(
            OLLAMA_URL + "/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=60.0,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()

        raw = re.sub(r"```(?:sql)?", "", raw).strip()
        raw = raw.strip("`").strip()

        match = re.search(r"(SELECT\b.+)", raw, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip().rstrip(";") + ";"
        return raw
    except Exception:
        # Ollama not available — try offline conversion
        sql = _offline_nl_to_sql(question)
        if sql:
            print(YELLOW + "  (offline mode — Ollama not reachable)" + RESET)
            return sql
        print("\n" + RED + "  x Ollama not reachable and no offline pattern matched." + RESET)
        print(DIM + "  Try typing SQL directly (starting with SELECT) or type 'help' for examples." + RESET)
        return ""


# ── MCP tool helpers ──────────────────────────────────────────────────────────
def _parse_mcp_result(result):
    """Parse the FastMCP CallToolResult into a Python dict."""
    if not result:
        return {}
    # FastMCP CallToolResult has .data (already-parsed dict) or .content (list of TextContent)
    if hasattr(result, "data") and result.data:
        return result.data
    if hasattr(result, "content"):
        for item in result.content:
            if hasattr(item, "text"):
                try:
                    return json.loads(item.text)
                except (json.JSONDecodeError, TypeError):
                    return {"raw": item.text}
    return {}


async def mcp_execute_query(session, sql):
    """Execute SQL via ch_execute_query MCP tool. Returns (rows, columns)."""
    result = await session.call_tool("ch_execute_query", {"sql": sql})
    parsed = _parse_mcp_result(result)

    # Response shape for ClickHouse: {'columns': [...], 'rows': [...]} or {'local': {'columns': [...], 'rows': [...]}}
    instances = parsed.get("results_per_instance", {})
    if not instances:
        # For ClickHouse it might be keyed by instance name like "local" directly
        if "local" in parsed and isinstance(parsed["local"], dict) and "columns" in parsed["local"]:
            instances = {"local": parsed["local"]}
        elif "columns" in parsed:
             instances = {"local": parsed}

    for inst_name, inst_data in instances.items():
        if "error" in inst_data:
            raise RuntimeError(f"ClickHouse error ({inst_name}): {inst_data['error']}")
        columns = inst_data.get("columns", [])
        rows_raw = inst_data.get("rows", [])
        # rows come as list of dicts from the connector
        if rows_raw and isinstance(rows_raw[0], dict):
            rows = [tuple(r.get(c, "") for c in columns) for r in rows_raw]
        elif rows_raw and isinstance(rows_raw[0], (list, tuple)):
            rows = [tuple(r) for r in rows_raw]
        else:
            rows = rows_raw
        return rows, columns

    return [], []


async def mcp_health_check(session):
    """Check ClickHouse health via ch_check_db_health MCP tool."""
    result = await session.call_tool("ch_check_db_health", {})
    parsed = _parse_mcp_result(result)

    instances = parsed.get("health_per_instance", {})
    if not instances and "local" in parsed:
        instances = {"local": parsed["local"]}

    health_info = {}
    for inst_name, data in instances.items():
        if "error" in data:
            raise RuntimeError(f"Health check failed ({inst_name}): {data['error']}")
        health_info[inst_name] = data

    return health_info


async def mcp_get_row_counts(session):
    """Get row counts for all e-commerce tables via MCP."""
    sql = (
        "SELECT 'customers' AS t, count() AS c FROM ecommerce.customers "
        "UNION ALL SELECT 'products', count() FROM ecommerce.products "
        "UNION ALL SELECT 'orders', count() FROM ecommerce.orders"
    )
    rows, _ = await mcp_execute_query(session, sql)
    return rows


# ── pretty print ──────────────────────────────────────────────────────────────
def print_results(rows, columns):
    if not rows:
        print("\n" + YELLOW + "  (no results)" + RESET + "\n")
        return
    print()
    print(tabulate(rows, headers=columns, tablefmt="rounded_outline", numalign="right"))
    print(DIM + "  " + str(len(rows)) + " row(s) returned" + RESET + "\n")


# ── banner ────────────────────────────────────────────────────────────────────
def print_banner():
    print(CYAN + BOLD + """
+----------------------------------------------------------+
|        ClickHouse NL Chatbot (E-commerce)                |
|        via MCP Server @ """ + MCP_URL + """          |
+----------------------------------------------------------+""" + RESET)
    print(DIM + "  Ask questions in plain English about customers, products & orders.")
    print("  Type " + BOLD + "exit" + RESET + DIM + " to quit, " + BOLD + "schema" + RESET + DIM + " to see tables, " + BOLD + "help" + RESET + DIM + " for examples." + RESET)
    print()


# ── main loop (async — MCP session stays open) ───────────────────────────────
async def main():
    print_banner()

    print(DIM + "  Connecting to ClickHouse MCP Server..." + RESET)

    try:
        async with mcp_client as session:
            # Health check via MCP
            try:
                health = await mcp_health_check(session)
                for inst_name, data in health.items():
                    ver = data.get("version", "unknown")
                    print(GREEN + f"  Connected via MCP → ClickHouse v{ver}" + RESET)

                row_counts = await mcp_get_row_counts(session)
                for t, c in row_counts:
                    print(DIM + f"    {t}: {c} rows" + RESET)
                print()
            except Exception as e:
                print(RED + f"  MCP health check failed: {e}" + RESET)
                print(DIM + "    Make sure the MCP server is running:" + RESET)
                print(DIM + "    .\\run.bat up" + RESET + "\n")
                sys.exit(1)

            # Interactive loop
            while True:
                try:
                    query = input(CYAN + BOLD + "You > " + RESET).strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n" + DIM + "Bye!" + RESET)
                    break

                if not query:
                    continue
                if query.lower() in ("exit", "quit", "q"):
                    print(DIM + "Bye!" + RESET)
                    break
                if query.lower() == "schema":
                    print(YELLOW + SCHEMA_CONTEXT + RESET)
                    continue
                if query.lower() == "help":
                    print(YELLOW + """
  Example queries:
    - List all customers
    - Show customers with at least 2 orders
    - What products did Rahul buy?
    - Total revenue per category
    - Top 3 customers by total spending
    - Which city has the most orders?
    - Average order value per customer
    - Show all orders
""" + RESET)
                    continue

                # If it's raw SQL, run directly via MCP
                if query.strip().upper().startswith("SELECT"):
                    sql = query
                    print("\n" + DIM + "  Running SQL via MCP..." + RESET)
                else:
                    print("\n" + DIM + "  Converting to SQL..." + RESET)
                    sql = nl_to_sql(query)
                    if not sql:
                        continue
                    print(GREEN + "  SQL: " + RESET + DIM + sql + RESET)

                try:
                    rows, cols = await mcp_execute_query(session, sql)
                    print_results(rows, cols)
                except Exception as e:
                    print("\n" + RED + "  Query failed: " + str(e) + RESET)
                    print(DIM + "  SQL was: " + sql + RESET + "\n")

    except Exception as e:
        print(RED + f"\n  Cannot connect to MCP Server at {MCP_URL}" + RESET)
        print(RED + f"  Error: {e}" + RESET)
        print(DIM + "\n  Make sure the ClickHouse MCP Server is running:" + RESET)
        print(BOLD + "    .\\run.bat up" + RESET + "\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
