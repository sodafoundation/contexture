<div align="center">
  <img src="https://sodafoundation.io/wp-content/uploads/2025/10/SODA_logo_outline_c.png" alt="SODA Foundation Logo" width="100"/>
  <p align="left">
    <br/>
  </p>
</div>

### SODA Contexture
The Open Context Engine for AI

### What is SODA Contexture?
SODA Contexture is an open source project under SODA Foundation (a sub-foundation under Linux Foundation). 
It is an open context building engine for AI.
SODA Contexture provides a platform to build enriched operational contexts to AI Agents for various data sources at scale. 
It improves the accuracy, efficiency, and speed of data inferences and insights significantly.

The project defines the Open Context Specification(OCS) to describe the data in a structured way. The specification provides the context implementation guidelines. 
SODA Contexture builds contexts using internal context agents based on OCS and also third party context sources.

### The key problems it solves
There is no standard way of communication to AI to get things done! 
Hence, the data inference and insights suffer from:
- Low Accuracy
   - The accuracy of results varies drastically based on the nature of data and inputs
   - Mixing guesses and different sources of knowledge confuses AI
- Inconsistency
   - Hallucination is key known issue with AI
- High Latency
  - Based on the type of query and volume of data, it fails to give ontime results
- Huge Cost
  - Iterations to get a close results and verification add costs
- Lack of Scale
  - Works for small amounts of data or 1 agent, when it comes to scale, it fails
- Low Reliability
  - Due to uncertain results AI is not fully dependable

One of the solutions to these problems is to provide the right context to the AI, for it to understand better to fetch the right pieces of data to derive the right inference. 
However this is not easy. Because, the data relationships and types can vary. That is why SODA Contexture is trying to solve the issue of “Missing Context” 
through OCS and building various components connecting to provide enriched and structured context.

### System Architecture
<img width="164" height="164" alt="image" src="https://github.com/user-attachments/assets/c9fc6cdd-8be9-4a1d-a825-ab5b7db10a28" />

SODA Contexture derives enriched context based on the OCS (Open Context Specification) implementation 
for the specific data sources and fills the issue of “Missing Context”. It builds the best possible 
context using its context building engine based on OCS for the input queries. Using this enhanced context
AI models can understand the context better and fetch the right data (or data sets) to provide accurate 
inferences and insights.

<img width="368" height="146" alt="image" src="https://github.com/user-attachments/assets/0529f34d-fa4f-44a4-8846-7ed973a4c0f6" />

#### SODA Contexture Ecosystem Comprises of:
- SODA Contexture Engine: The core component that processes user requests and orchestrates context generation.
- Open Context Specification: The specification which details the operational context building attributes for various types of data.
- Data Connectors: Logical Connectors to different types of data such as prometheus, sql, s3 and so on to understand the nature of data storage and layout. These connectors provide SODA Contexture a better idea to use the OCS to build the context better. These are logical connectors for specific data source
- Context Providers: Sources that provide enriched context information (e.g., Istio, Kubernetes).

### Open Context Specification (OCS)
OCS (Open Context Specification) provides the specification for operational data context spec for different kinds of data sources. It provides the key attributes to derive the best possible context to enable AI to provide more accurate results.

OCS Defines the key attributes to build the operational context:
- Identity and Origin (The "Who" and "Where")
  - Defines the unique fingerprint of the data source. 
  - AI needs this to distinguish between similar metrics from different environments
- Dimensionality & Topology (The "Relationship")
  - Defines how this metric relates to other components
  - This is the most critical part for AI reasoning.
- Metric Semantics (The "What")
  - Define what the number actually represents
  - This will avoid the AI comparing unrelated metrics.
- Temporal Context (The "When")
  - AI needs to know if it's looking at a "point-in-time" value or a trend.
  - Interval, Duration, Time stamp etc
- Operational Constraints (The "How")
  - This tells the AI how to interpret the health of the metric.
  - Threshold, Polarity, Aggregation

### Progress 
#### Supported Data Connectors
- Prometheus
- postgres - developing
- ceph - analysing
- s3 - analysing
- ? [Please suggest]
#### Supported Context Providers
- istio
- ? [Please suggest]
We are actively developing the project. So if you would like to join the design, OCS and other components, please join us!

#### Design
- [OCS RFC] (https://docs.google.com/document/d/1XHN8NuXTPqKWOikFALfCTZHt6JCDpsHS)
- [Architecture Design Doc] (https://docs.google.com/document/d/1uV_1DudI_Q9xaifFEUcZvXsX8sKGIpKo)

## Recommended Startup Order

1. Start Prometheus
2. Start Ollama
3. Run OCS Service (optional)
4. Run MCP Server (optional)
5. Run Contexture CLI

## Local Setup & Execution Guide

This guide walks you through the steps required to set up and run the Soda Contexture codebase locally.

---

## Prerequisites

Ensure the following services are installed and running before proceeding:

- **Prometheus**  
  A running instance of Prometheus is required.  
  [Official Getting Started Guide](https://prometheus.io/docs/prometheus/latest/getting_started/)

- **Ollama**  
  A running Ollama instance is required.  
  [Installation Guide](https://docs.ollama.com/)

- **Model Setup**  
  Download a model in Ollama (example):  
  ```bash
  ollama pull qwen2.5-coder:7b
  ```  
  You can pull any model suitable for your system (considering RAM, compute, and response time). Larger models may be slow or fail to run on machines with limited resources, so choose a smaller or lighter model if needed (for example, `qwen2.5-coder:3b` or `qwen2:0.5b` or another smaller variant).

---

## Step 1: Create a Virtual Environment

```bash
python -m venv .venv
```

It is recommended to use a stable Python version (for example, Python 3.12) because some dependencies may not install correctly on very recent or development versions (such as Python 3.14). On Windows with multiple Python versions, you can create the environment like:

```bash
py -3.12 -m venv .venv
```
---

## Step 2: Activate the Virtual Environment

- **Windows:**  
  ```bash
  .venv\Scripts\activate
  ```

- **Mac / Linux:**  
  ```bash
  source .venv/bin/activate
  ```

---

## Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Step 4: Onboarding (Dynamic Prompt Mode)

Before running the CLI, you must generate embeddings for your metrics:

```bash
python pkg/copilot/DP_logic/DynamicPrompt/onboarding_cli.py
```

During execution: enter the path to your metrics file (for example: `config/metrics.txt`), or press `Enter` to use the default path.

Embeddings will be created in:  
`config/embeddings/`

---

## Step 5: Configuration

### Ollama Configuration

Edit `ollama_config.yaml` and set the host where Ollama is running:

```yaml
host: "http://localhost:11434/api/generate"
```

### Prometheus Configuration

Edit `prometheus_config.yaml` and set the Prometheus URL:

```yaml
prometheus_url: "http://localhost:9090"
```

### DP Logic Configuration

In `pkg/copilot/DP_logic/dp_logic.py`, also make sure the Ollama configuration and the model you are using, as well as the Prometheus URL, are correctly set. For example:

```python
OLLAMA_URL = OLLAMA_CONFIG.get("ollama_url", "http://localhost:11434/api/generate")
OLLAMA_MODEL = OLLAMA_CONFIG.get("ollama_model", "qwen2:0.5b")
```

For Prometheus, ensure the connection URL is set correctly:

```python
prom = PrometheusConnect(
    url="http://localhost:9090",
)
```

### Environment Variables

Create a `.env` file and add the following (use absolute paths):

```bash
EMBEDDING_PATH="/absolute/path/to/ts-ai-agent/pkg/copilot/DP_logic/DynamicPrompt/config/embeddings/embeddings.npz"
TEMPLATE_PATH="/absolute/path/to/ts-ai-agent/pkg/copilot/DP_logic/DynamicPrompt/config/template_sections"
OVERRIDE_PATH="/absolute/path/to/ts-ai-agent/pkg/copilot/DP_logic/DynamicPrompt/config/overrides.json"
EXAMPLES_PATH="/absolute/path/to/ts-ai-agent/pkg/copilot/DP_logic/DynamicPrompt/config/golden_examples.json"
INFO_PATH="/absolute/path/to/ts-ai-agent/pkg/copilot/DP_logic/DynamicPrompt/config/additional_context.json"
```

---

## Step 6: Running the CLI

Run the CLI with a query set:

```bash
python pkg/cli.py \
  --query-set test/query_sets/example1.yaml \
  --copilot DYNAMIC_PROMPT \
  --prometheus-config config/prometheus_config.yaml
```

---

## Step 7: Query Set Format

Example YAML query file:

```yaml
queries:
  - "Which cluster has highest CPU utilisation?"
  - "Which cluster has the highest memory allocation?"
```

---

## Step 8: Output Format

Results are generated as YAML files in the `output/` directory:

```yaml
"Your question here":
  final: "Final human-readable summary or conclusion"
  ollama_response: "Detailed step-by-step reasoning or intermediate generation from LLM"
  promql: "raw PromQL query"
  result: "Output results of PromQL execution"
  error: "Optional error message if something went wrong"
```

---

## Prometheus-Powered MCP AI Observability Agent

This project implements a **Model Context Protocol (MCP)** that provides intelligent, real-time observability over Kubernetes clusters using **Prometheus metrics** and **LLM-based reasoning**.  

It exposes monitoring tools (like CPU usage, pod anomalies, and disk pressure) as callable APIs that an **AI assistant** or **chatbot** can query using natural language.

---

## 🚀 Features

- 🌐 Supports **multiple Prometheus instances** (multi-cluster setup)
- 🤖 Integrated with **Ollama LLMs** (e.g., `qwen2.5-coder:14b`)
- ⚙️ Built on **FastMCP** for tool registration and invocation
- 📊 Provides tools for:
  - Pod and node metric summaries
  - CrashLoop detection
  - Disk pressure alerts
  - CPU/memory anomaly detection
  - Correlated metric analysis
  - Event timelines and trend detection
- 🧩 Ready for integration with any monitoring chatbot

---

## MCP Setup Guide

The following section describes how to configure and run the Model Context Protocol (MCP) components of SODA Contexture.

---

## ⚙️ Prerequisites

You’ll need the following installed:

- **Python 3.9+**
- **Minikube** (for running Kubernetes clusters)
- **Prometheus** (deployed on each cluster)
- **Ollama** (for local LLM inference)
- **FastMCP** Python package

---

### Practical Minimal Setup

If you’re running:

- Ollama with a 7B model (default: llama3 or mistral)  
- FastMCP server and client on the same machine  

#### ✅ CPU-Only Setup
- **CPU:** 8 cores (Intel i7 / AMD Ryzen 7 or better)  
- **RAM:** 16 GB  
- **Storage:** SSD (10+ GB free for model files)  
- **OS:** Ubuntu 22.04+ / macOS / WSL2 on Windows  
- **Performance:** Each query takes ~5–15 seconds depending on model size  

#### ⚡ GPU-Accelerated Setup (Recommended)
- **GPU:** NVIDIA RTX 3060 (12 GB VRAM) or better  
- **CPU:** 6+ cores  
- **RAM:** 16 GB  
- **Speed:** 5×–10× faster responses from Ollama


## 🧰 Configuration

Edit `config/{}_config.yaml` as follows:

```yaml
# Server Config
mcp_server_url: "http://localhost:8001/mcp"


# LLM Configuration
ollama_url: "http://localhost:11434"
ollama_model: "qwen2.5-coder:14b"

# Prometheus Instances
prometheus_instances:
  - name: prometheus_1
    base_url: "http://localhost:9090"
    headers: {}
    disable_ssl: false

  - name: prometheus_2
    base_url: "http://localhost:9091"
    headers: {}
    disable_ssl: false
```

##  Setting Up Prometheus on Two Minikube Clusters

You can simulate a multi-cluster environment using two Minikube clusters:

```yaml
# Create two clusters
minikube start -p minikube1
minikube start -p minikube2

Enable Prometheus in both clusters:

kubectl create namespace monitoring
kubectl apply -f https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/main/bundle.yaml

Forward ports locally:

# Cluster 1
kubectl --context=minikube1 -n monitoring port-forward svc/prometheus-operated 9090:9090

# Cluster 2
kubectl --context=minikube2 -n monitoring port-forward svc/prometheus-operated 9091:9090
```

Prometheus instances are now accessible at:

    http://localhost:9090 (Cluster 1)

    http://localhost:9091 (Cluster 2)

## 🚀 Running the MCP Server

Start the MCP server: 

```bash
fastmcp run server.py:app --transport http --port 8001
```

Run the client:

```bash
python3 client_dynamic.py
```

## 🧪 Running Tests

Validate all MCP tools using the provided integration test suite:

```bash
pytest -v test_mcp_tools.py
```

This test suite:

Iterates through all MCP tools

Calls each tool via the MCP API

Verifies each tool returns a valid JSON response

## 🤝 Contributing

We welcome contributions to improve and extend the **Prometheus-Powered MCP AI Observability Agent**!  
Whether you’re fixing a bug, improving documentation, or adding a new observability tool, your help makes the project better for everyone.

## 🛠️ Adding a New MCP Tool

Adding a new tool lets the **AI observability agent** expose more **Prometheus-powered capabilities** to LLMs.

### Steps

1. **Define your tool function in `pkg/mcp/server.py`**

   Each tool should:
   - Use the `@app.tool()` decorator  
   - Accept keyword arguments (using parameters or `**kwargs`)  
   - Return a valid **JSON-serializable Python dictionary**  
   - Handle exceptions gracefully  

   Example:
   ```python
   @app.tool()
    def your_new_tool_name(**kwargs) -> Dict[str, Any]:
    """
    Short description of what this tool does.
    """
    try:
        # ✅ Step 1: Validate input arguments
        if "some_required_arg" not in kwargs:
            return {"error": "Missing required argument: some_required_arg"}
        
        # ✅ Step 2: Perform Prometheus query or computation
        # Example placeholder for querying Prometheus
        query = f"your_prometheus_metric{{label='{kwargs['some_required_arg']}'}}"
        response = prometheus_client.custom_query(query=query)
        
        # ✅ Step 3: Parse and structure the response
        results = []
        for item in response:
            try:
                value = float(item["value"][1])
            except (KeyError, ValueError, IndexError):
                value = None
            results.append({
                "label": kwargs["some_required_arg"],
                "value": value
            })
        
        # ✅ Step 4: Return a JSON-serializable response
        return {
            "metric": "your_prometheus_metric",
            "results": results,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        # ✅ Step 5: Handle unexpected errors gracefully
        return {"error": str(e)}
  ```

---
2. **Register the Tool**

   After defining your tool, make sure it is properly **registered** with the MCP server so it can be discovered and invoked by the AI observability agent.

   ### Steps:
   1. **Add your tool function** to the MCP app (usually in `server.py`) using the `@app.tool()` decorator.
   2. Ensure your MCP server automatically loads tools from the same file or explicitly imports them into the tool registry.
   3. **Restart** the MCP server to apply your changes.

   ### Verify Your Tool
   Run the existing test suite to confirm that your new tool works correctly:

   ```bash
    pytest -v test_mcp_tools.py
   ```

---

## Contexture OCS Service

<div align="center">
  <img src="https://www.loginradius.com/assets/blog/engineering/istio-service-mesh/Istio.webp" alt="Istio" height="80" style="margin: 0 15px;">
  <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/3/38/Prometheus_software_logo.svg/1280px-Prometheus_software_logo.svg.png" alt="Prometheus" height="80" style="margin: 0 15px;">
  <img src="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRtovlsBMk0rvY-OWj2EzOc0yLnIRZWY4Pedw&s" alt="Prometheus" height="80" style="margin: 0 15px;">
</div>

A Go-based service that collects service mesh metrics from Prometheus, builds workload topology, and provides context definitions for observability analysis

## Overview

The OCS Server provides:
- **Istio Metrics Collection**: Queries Prometheus for `istio_requests_total` metrics filtered by source workloads
- **Topology Building**: Extracts source-destination workload relationships and stores them as adjacency lists in MongoDB
- **Context Definitions**: Provides structured context information combining topology, metrics, and policies for observability analysis

## OCS Setup Guide
The following section describes how to configure and run the Open Context Specification (OCS) service components.

## Prerequisites

- Go 1.21 or higher
- MongoDB (running locally or accessible via `MONGODB_URI`)
- Prometheus (with Istio metrics exposed)
- Access to Prometheus API endpoint

## Installation

1. **Install dependencies**:
```bash
go mod tidy
```

2. **Configure MongoDB** (optional, defaults to `mongodb://localhost:27017/`):
```bash
export MONGODB_URI="mongodb://localhost:27017/"
export MONGODB_DB_NAME="ocs"
```

3. **Configure server port** (optional, defaults to 8000):
```bash
export PORT="8000"
```

4. **Ensure Prometheus is configured** in `config/prometheus_config.yaml`

5. **Configure OCS settings** in `pkg/ocs/ocs_config.yaml`

## Configuration

### OCS Config (`ocs_config.yaml`)

```yaml
policy:
  - "sla violation if cpu utilization is greater than 90%"

metrics:
  - name: "cpu_utilization"
    type: "gauge"
    unit: "percentage"
    description: "Current CPU usage against pod limits"
    aggregation_logic: "average"
    health_config:
      critical_threshold: 90
      polarity: "high_is_bad"

workload:
  - database
  - cache
  - app
  - proxy

time_window_minutes: 5  # Optional: auto time window for queries
```

### Prometheus Config (`config/prometheus_config.yaml`)

```yaml
prometheus_instances:
  - name: prometheus_1
    base_url: "http://localhost:9090"
    headers: {}
    disable_ssl: false
```

## Running the Server

### Development Mode

```bash
# Run all files in the package
go run ./pkg/ocs/

# Or specify all files explicitly
go run pkg/ocs/*.go
```

### Production Mode

```bash
# Build the binary
go build -o ocs-server ./pkg/ocs/

# Run the binary
./ocs-server
```

## API Endpoints

### GET `/get_ocs_prompt`

Returns OCS context definitions combining topology from MongoDB, metrics, and policies from config.

**Response:**
```json
{
  "spec_version": "0.1",
  "context_definitions": [
    {
      "resource_id": "workload-database",
      "domain": "compute.k8s",
      "identity": {
        "workload": "database"
      },
      "metrics": [...],
      "topology": {
        "dependencies": ["cache", "app"],
        "dependents": ["proxy"]
      },
      "policy": ["sla violation if cpu utilization is greater than 90%"]
    }
  ]
}
```

**Example:**
```bash
curl http://localhost:8000/get_ocs_prompt
```

### POST `/collect_istio_metrics`

Queries Prometheus for Istio request metrics, extracts workload topology, and saves to MongoDB.

**Query Parameters (optional):**
- `from_timestamp`: Start time (RFC3339 or Unix timestamp)
- `to_timestamp`: End time (RFC3339 or Unix timestamp)

If timestamps are not provided and `time_window_minutes` is configured, uses automatic time window.

**Response:**
```json
{
  "status": "success",
  "message": "Metrics collected and saved to MongoDB",
  "adjacency_list": {
    "database": ["cache", "app"],
    "app": ["database"]
  },
  "document_id": "507f1f77bcf86cd799439011",
  "timestamp": "2024-01-01T00:00:00Z",
  "from_timestamp": "2024-01-01T00:00:00Z",
  "to_timestamp": "2024-01-01T00:05:00Z",
  "time_window_minutes": 5
}
```

**Examples:**
```bash
# Use configured time window (5 minutes)
curl -X POST http://localhost:8000/collect_istio_metrics

# Use custom time range
curl -X POST "http://localhost:8000/collect_istio_metrics?from_timestamp=2024-01-01T00:00:00Z&to_timestamp=2024-01-01T23:59:59Z"

# Use Unix timestamps
curl -X POST "http://localhost:8000/collect_istio_metrics?from_timestamp=1704067200&to_timestamp=1704153600"
```

### GET `/health`

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "prometheus": true,
  "mongodb": true,
  "timestamp": "2024-01-01T00:00:00Z"
}
```

**Example:**
```bash
curl http://localhost:8000/health
```

## MongoDB Schema

The adjacency list is stored in the `workload_adjacency` collection:

```json
{
  "_id": ObjectId("..."),
  "adjacency_list": {
    "source_workload": ["destination1", "destination2"]
  },
  "timestamp": ISODate("..."),
  "source_count": 2,
  "total_connections": 3
}
```

## Troubleshooting

### "MongoDB not initialized" error
- Check MongoDB is running
- Verify `MONGODB_URI` environment variable
- Check connection string format

### "Prometheus query failed" error
- Verify Prometheus is accessible at configured URL
- Check network connectivity
- Verify Istio metrics are being scraped

### "No source workloads configured" error
- Ensure `workload` list is populated in `ocs_config.yaml`
- Check YAML syntax is correct

## Prometheus Data Generator for Kubernetes Clusters
Prometheus High-Cardinality Data Generator for Kubernetes Clusters
This script generates and pushes high-cardinality time-series data to Prometheus
simulating multiple Kubernetes clusters with one year of historical data.

## Key feature
The script simulates multiple Kubernetes clusters with realistic high-cardinality metrics including CPU usage, memory consumption, network traffic, disk I/O, pod status, and node metrics. It uses the Prometheus Remote Write API protocol for efficient data transmission.​

## Prerequisite
1. The remote-write needs to enabled in prometheus. To enable the remote-write in prometheus instance make sure it is configured at run time using ```--web.enable-remote-write-receiver```
2. TSDB out of order time window: Prometheus consider only 1-2 hour maximum of out of order time series data. Since the range of data push in our case vary, increase the out of order time window to match days of history. Config parameter to be changed:
```yaml
storage:
  tsdb:
    out_of_order_time_window: 15d
```

## Installation
First, install the required dependency:

```bash
pip install prometheus-remote-writer
```

## Usage Options
Command-Line Arguments

``` bash
# Basic usage
python prometheus_data_pusher.py --url http://localhost:9090/api/v1/write
```

```bash
# With custom parameters
python prometheus_data_pusher.py \
    --url http://localhost:9090/api/v1/write \
    --clusters 10 \
    --days 365 \
    --batch-size 1000 \
    --scrape-interval 30
```

Run with config file:

```bash
python prometheus_data_pusher.py --config config.json
```

## Generated Metrics
The script generates 15+ metric types per container:​

##### Container Metrics:

```
container_cpu_usage_seconds_total - CPU usage tracking

container_cpu_cfs_throttled_seconds_total - CPU throttling events

container_memory_usage_bytes - Memory consumption

container_memory_working_set_bytes - Active memory

container_memory_cache - Cached memory

container_network_receive_bytes_total - Network ingress

container_network_transmit_bytes_total - Network egress

container_network_receive_errors_total - Network errors

container_fs_reads_bytes_total - Disk reads

container_fs_writes_bytes_total - Disk writes
```

#### Pod Metrics:

```
kube_pod_status_phase - Pod lifecycle status

kube_pod_container_status_restarts_total - Container restart count
```

#### Node Metrics:

```
kube_node_status_capacity_cpu_cores - Node CPU capacity

kube_node_status_capacity_memory_bytes - Node memory capacity

kube_node_status_condition - Node health status
```

#### High Cardinality Labels
Each metric includes multiple labels to simulate real-world high-cardinality scenarios:​

```
cluster - Cluster identifier (e.g., k8s-cluster-001)

namespace - Kubernetes namespace

pod - Unique pod name with random identifier

container - Container name

node - Node hostname

region - Cloud region (us-east-1, eu-west-1, etc.)

environment - Environment type (production, staging, development)

app - Application name

version - Application version (semantic versioning)

instance_type - Node instance type (t3.large, m5.xlarge, etc.)
```

Cardinality Estimation
With default configuration, the script generates approximately 13.5 million unique time series:

```
10 clusters × 50 nodes × 20 namespaces × 30 pods × 3 containers × 15 metrics = ~13,500,000 time series
```

## Quickstart
```bash
# Setup environment

python -m venv .venv
. .venv/bin/activate
pip install prometheus-remote-writer

# Running local prometheus server
docker volume create prometheus-data

--prometheus.yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

remote_write:
  - url: "http://localhost:9090/api/v1/write" # Replace with your actual remote write endpoint
    queue_config:
      max_samples_per_send: 100000
      capacity: 100000

storage:
  tsdb:
    out_of_order_time_window: 15d


docker run -d \
  --name prometheus-remote-write \
  -p 9090:9090 \
  -v prometheus-data:/prometheus \
  -v ./prometheus.yaml:/etc/prometheus/prometheus.yaml \
  --memory="4g" \
  --cpus="3" \
  prom/prometheus \
  --config.file=/etc/prometheus/prometheus.yaml \
  --web.enable-remote-write-receiver

python prometheus_data_pusher.py --config config.json
```

---

### How to join the development?
  - [GitHub](https://github.com/sodafoundation/contexture)
  - [SODA Slack](https://sodafoundation.slack.com)


