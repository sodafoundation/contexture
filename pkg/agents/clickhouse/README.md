# ClickHouse MCP Agent

A ClickHouse data-connector agent for [SODA Contexture](https://github.com/sodafoundation/contexture).  
Exposes ClickHouse databases, tables, and query execution as MCP tools via [FastMCP](https://github.com/jlowin/fastmcp).

---

## How to Run

The easiest way to run the ClickHouse agent (including a local database, schema initialization, and the MCP agent itself) is using the provided Docker stack and `run.bat` launcher from the repository root.

### 1. Start the Stack

From the root of the repository, run:

```bash
.\run.bat up
```

This will:
- Start a ClickHouse database on ports `9000` (native) and `8123` (HTTP).
- Automatically seed the database with sample schemas (`ecommerce`, `metrics`, etc).
- Build and start the `contexture-clickhouse-mcp` FastMCP agent on `http://localhost:8004/sse`.

### 2. Verify and Test

To verify the agent's internal routing logic is healthy, run:

```bash
.\run.bat test
```

### 3. Interactive NL Chatbot

An interactive terminal-based Natural Language chatbot is provided in `scripts/clickhouse/chatbot.py`. It uses Ollama to translate natural language into SQL against the ClickHouse `ecommerce` schema, and routes it through the MCP Server.

To use it, ensure the stack is running (`.\run.bat up`), then run:

```bash
py scripts\clickhouse\chatbot.py
```

**Try asking it:**
- *"List all customers"*
- *"What products did Rahul buy?"*
- *"Total revenue per category"*
- *"Top 3 customers by total spending"*
- *"Which city has the most orders?"*
- *"Average order value per customer"*

### 4. Stop the Stack

```bash
.\run.bat down
```
