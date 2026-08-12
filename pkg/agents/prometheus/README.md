# Prometheus Agent — SODA Contexture

A **FastMCP-based Prometheus data connector** for SODA Contexture.  
It exposes Prometheus metrics as MCP tools so the Contexture engine (backed by a **local Ollama model**) can query, analyse, and build enriched OCS context from Kubernetes observability data.

---

## Folder Structure

```
pkg/agents/prometheus/
├── server.py                  # FastMCP entry point — all @app.tool() definitions
├── prometheus_connector.py    # PrometheusConnect factory and config loading
├── mcp_tools.py               # Tool wrapper functions (callable without the server)
├── tool_registry.py           # TOOLS dict — mirrors postgres/tool_registry.py
├── agent.py                   # Keyword-based NL query router
├── data_pusher.py             # High-cardinality test data generator (Remote Write)
├── config.json                # Sample config for data_pusher.py
├── test_connection.py         # Quick connectivity test — run this first
├── requirements.txt           # Python dependencies
└── README.md

config/
└── prometheus_config.yaml     # Multi-instance connection config (repo root)
```

---

## Architecture

```
Ollama (local LLM)
      │  NL query → workflow JSON
      ▼
pkg/mcp/client_dynamic.py        (full LLM-based routing, any adaptor)
      │  — or —
agent.py                         (keyword-based routing, Prometheus only)
      │  call_tool(name, params)
      ▼
server.py  (FastMCP — default port 8001)
      │  @app.tool() handlers
      ▼
prometheus_connector.py  (PrometheusConnect, multi-instance)
      │  PromQL queries
      ▼
Prometheus
```

The flow is identical to how other SODA Contexture data-connector agents work.  
The OCS engine fetches context from `/get_ocs_prompt`, the LLM converts the NL query into a list of tool calls, and the FastMCP client executes them against this server.

---

## Available MCP Tools

| Tool | Description |
|---|---|
| `explain_ocs_policy` | Parse and explain the OCS config (policy statements, thresholds, workloads) |
| `current_metric_for_pods` | Instant value of any metric for a given list of pods |
| `workload_metrics` | Aggregate a metric by workload (`app` label), with optional time window |
| `top_n_pods_by_metric` | Top N pods by average metric value over a window |
| `pod_network_io` | Network receive/transmit rates (bytes/sec) per pod |
| `pods_exceeding_cpu` | Pods whose CPU rate exceeds a threshold |
| `pods_exceeding_memory` | Pods whose memory usage exceeds a threshold |
| `pod_status_summary` | Count of pods in each lifecycle phase (Running, Pending, Failed, …) |
| `recent_pod_events` | Most recent Kubernetes pod events by reason |
| `node_disk_usage` | Average and peak disk usage (%) per node over a time window |
| `node_memory_usage` | Average and peak memory usage (%) per node over a time window |
| `top_disk_pressure_nodes` | Nodes with disk usage above a threshold |
| `top_memory_pressure_nodes` | Nodes with memory usage above a threshold |
| `describe_cluster_health` | Plain-English cluster health summary from pod phase counts |
| `pod_restart_trend` | Top pods by restart count over a recent window |
| `detect_pod_anomalies` | Z-score anomaly detection across pods for any metric |
| `namespace_resource_summary` | CPU or memory usage broken down by namespace |
| `detect_crashloop_pods` | Pods in or approaching CrashLoopBackOff |
| `correlate_metrics` | Pearson correlation between two metrics across pods |
| `pod_event_timeline` | Snapshot of restarts, network I/O, and CPU for a specific pod |
| `node_condition_summary` | Nodes with non-Ready conditions (MemoryPressure, DiskPressure, …) |

All tools iterate over every instance in `prometheus_config.yaml` and return results keyed by instance name — same pattern as other agents returning `*_per_prometheus`.

---

## Configuration

Edit `config/prometheus_config.yaml` at the project root:

```yaml
prometheus_instances:
  - name: prometheus_1
    base_url: "http://localhost:9090"
    headers: {}
    disable_ssl: false

  # Add more instances as needed (e.g. multi-cluster):
  # - name: prometheus_2
  #   base_url: "http://localhost:9091"
  #   headers: {}
  #   disable_ssl: false
```

Ollama and MCP server URLs are configured in `config/ollama_config.yaml` and `config/mcp_server_config.yaml`.

---

## Getting Started & Integrated Launch

To bring up the entire integrated ecosystem (the Prometheus MCP Agent, the MongoDB database seeding, the UI Backend Gateway, and the React Web App) in the simplest way, follow these steps.

### 1. One-Time Setup (Shared Virtual Environment)
Instead of creating multiple python environments, create and activate a single shared virtual environment in the parent workspace directory:

```bash
cd "D:\Caze Labs\SodaFoundation"
python -m venv venv

# Activate (Linux/WSL: source venv/bin/activate | Windows: .\venv\Scripts\activate)
source venv/bin/activate

# Install all packages at once
pip install -r contexture-fork/contexture/requirements.txt
pip install -r contexture-ui/backend/requirements.txt python-dotenv
```

### 2. Seed MongoDB Context (Run once)
Verify MongoDB is running on `localhost:27017` and seed the OCS context metadata from your static JSON file. You can optionally specify a custom path to your context file (defaults to `generated_ocs_context.json`):

```bash
python contexture-fork/contexture/scratch/seed_mongo.py [custom_context_file.json]
```

### 3. Launch the Services (Multi-terminal)
Run the following processes concurrently (each terminal should have the shared virtual environment `venv` active):

#### Terminal 1: Start Prometheus MCP Server (Port 8001)
* **Linux/WSL**:
  ```bash
  export PYTHONPATH=contexture-fork/contexture/pkg/agents/prometheus
  python contexture-fork/contexture/pkg/agents/prometheus/server.py --transport sse --port 8001
  ```
* **Windows (PowerShell)**:
  ```powershell
  $env:PYTHONPATH="contexture-fork/contexture/pkg/agents/prometheus"
  python contexture-fork/contexture/pkg/agents/prometheus/server.py --transport sse --port 8001
  ```

#### Terminal 2: Start Copilot Backend (Port 8002)
This runs the core reasoning client that coordinates with the MCP server:
```bash
python -m pkg.mcp.client_dynamic_ui
```

#### Terminal 3: Start UI Backend Gateway (Port 8003)
Start the proxy gateway server on port 8003 (matching the React frontend configuration):
* **Linux/WSL**:
  ```bash
  USE_REAL_AGENT=true TS_AGENT_PATH=$(pwd)/contexture-fork/contexture python contexture-ui/backend/main.py
  ```
* **Windows (PowerShell)**:
  ```powershell
  $env:USE_REAL_AGENT="true"; $env:TS_AGENT_PATH="$pwd\contexture-fork\contexture"; python contexture-ui/backend/main.py
  ```

#### Terminal 4: Start React Frontend (Port 5173)
Start the web development server to view the interface:
```bash
cd contexture-ui/frontend
npm install && npm run dev
```

Open your browser to `http://localhost:5173/` to run your natural language queries!

---

## Setting Up Prometheus on Minikube (Multi-Cluster Example)

```bash
# Start two clusters
minikube start -p minikube1
minikube start -p minikube2

# Deploy Prometheus on each
kubectl --context=minikube1 create namespace monitoring
kubectl --context=minikube1 apply -f https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/main/bundle.yaml

kubectl --context=minikube2 create namespace monitoring
kubectl --context=minikube2 apply -f https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/main/bundle.yaml

# Port-forward locally
kubectl --context=minikube1 -n monitoring port-forward svc/prometheus-operated 9090:9090 &
kubectl --context=minikube2 -n monitoring port-forward svc/prometheus-operated 9091:9090 &
```

Then add both to `config/prometheus_config.yaml`.

---

## Generating Test Data

`data_pusher.py` generates high-cardinality Kubernetes metrics and pushes them via the Prometheus Remote Write API. Useful for testing without a live cluster.

**Prerequisites:** enable remote write receiver in Prometheus:

```
--web.enable-remote-write-receiver
```

And increase the out-of-order time window for historical data:

```yaml
storage:
  tsdb:
    out_of_order_time_window: 15d
```

**Run:**

```bash
# With config file (edit config.json for scale)
python data_pusher.py --config config.json

# Or with inline flags
python data_pusher.py \
    --url http://localhost:9090/api/v1/write \
    --clusters 2 \
    --days 1 \
    --batch-size 100 \
    --scrape-interval 60
```

Default `config.json` pushes a small dataset (2 clusters, 1 day) suitable for quick testing.

---

## Adding a New Tool

1. Add a query function (or inline the query) in `mcp_tools.py`.
2. Register it in `tool_registry.py`.
3. Add an `@app.tool()` in `server.py` that calls `_instances()` + `get_client()`.
4. Optionally add a keyword branch in `agent.py` for direct NL routing.
