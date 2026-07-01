# ClickHouse MCP Agent

A ClickHouse data-connector agent for [SODA Contexture](https://github.com/sodafoundation/contexture).  
Exposes ClickHouse databases, tables, and query execution as MCP tools via [FastMCP](https://github.com/jlowin/fastmcp),
following the same pattern as the PostgreSQL and MongoDB agents.

---

## File Structure

```
pkg/agents/clickhouse/
├── agent.py                  # Natural-language query router
├── clickhouse_connector.py   # Low-level ClickHouse connection & queries
├── mcp_tools.py              # Tool wrapper functions (callable without server)
├── server.py                 # FastMCP server exposing all tools
├── test_connection.py        # Quick connectivity test
├── tool_registry.py          # Central TOOLS registry
├── requirements.txt          # Python dependencies
└── README.md                 # This file

config/
└── clickhouse_config.yaml    # ClickHouse instance connection settings
```

---

## Setup

### 1. Install dependencies

```bash
cd pkg/agents/clickhouse
pip install -r requirements.txt
```

### 2. Configure ClickHouse connection

Edit `config/clickhouse_config.yaml` at the repo root:

```yaml
clickhouse_instances:
  - name: local
    host: "localhost"
    port: 9000
    database: "default"
    username: "default"
    password: ""
    secure: false
```

### 3. Test the connection

```bash
cd pkg/agents/clickhouse
python test_connection.py
```

---

## Running the MCP Server

```bash
cd pkg/agents/clickhouse

# stdio transport (default — for use with MCP clients)
python server.py

# SSE/HTTP transport on port 8004
python server.py --transport sse

# SSE on a custom port
python server.py --transport sse --port 9000
```

---

## Available MCP Tools

| Tool | Description |
|---|---|
| `ch_list_databases` | List all databases with engine info |
| `ch_list_tables` | List tables in a database with row count and size |
| `ch_describe_table` | Show columns, types, and storage info for a table |
| `ch_execute_query` | Run a read-only SELECT query |
| `ch_get_table_stats` | Storage stats: size, engine, partition/sorting keys |
| `ch_get_db_stats` | Server-level metrics (connections, active queries) |
| `ch_get_slow_queries` | Top slow queries from `system.query_log` (last 24h) |
| `ch_check_db_health` | Version, uptime, connections, running queries |

---

## Docker (local ClickHouse)

A ClickHouse instance is included in `docker-compose.yml` at the repo root:

```bash
docker-compose up -d clickhouse
```

Then initialise the schema:

```bash
docker exec -i contexture-clickhouse clickhouse-client < scripts/clickhouse/init.sql
```

---

## See Also

- [PostgreSQL Agent](../postgres/README.md)
- [MongoDB Agent](../mongodb/README.md)
- [ClickHouse Documentation](https://clickhouse.com/docs)
