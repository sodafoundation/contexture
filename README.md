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
  - Based on the type of query and volume of data, it fails to give on time results
- Huge Cost
  - Iterations to get close results and verification add costs
- Lack of Scale
  - Works for small amounts of data or 1 agent, when it comes to scale, it fails
- Low Reliability
  - Due to uncertain results AI is not fully dependable

One solution to these problems is to provide the right context to the AI, for it to understand better to fetch the right pieces of data to derive the right inference. 
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
- Data Connectors: Logical connectors to different types of data such as prometheus, sql, s3 and so on to understand the nature of data storage and layout. These connectors provide SODA Contexture a better idea to use the OCS to build the context better. These are logical connectors for specific data source
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

---

## 🚀 Quick Start (5 minutes)

### Prerequisites

Ensure the following services are installed and running before proceeding:

- **Prometheus**  
  A running instance of Prometheus is required.  
  [Official Getting Started Guide](https://prometheus.io/docs/prometheus/latest/getting_started/)

- **Ollama**  
  A running Ollama instance is required.  
  [Installation Guide](https://docs.ollama.com/)

- **Model Setup**  
  Download a model in Ollama (example): ollama pull qwen2.5-coder:7b

### Setup 

```bash
python -m venv .venv 
source .venv/bin/activate           # Windows: .venv\Scripts\activate 
pip install -r requirements.txt
```

### Configuration

#### Ollama Configuration

Edit `ollama_config.yaml` and set the host where Ollama is running:

```yaml
host: "http://localhost:11434/api/generate"
```

####  Prometheus Configuration

Edit `prometheus_config.yaml` and set the Prometheus URL:

```yaml
prometheus_url: "http://localhost:9090"
```

### Generate Embeddings (one-time)

Before running the CLI, you must generate embeddings for your metrics:

```bash
python pkg/copilot/DP_logic/DynamicPrompt/onboarding_cli.py
```
Embeddings will be created in:  
`config/embeddings/`

### Run the CLI with a query set

```bash
python pkg/cli.py \
  --query-set test/query_sets/example1.yaml \
  --copilot DYNAMIC_PROMPT \
  --prometheus-config config/prometheus_config.yaml
```

Example query file`(test/query_sets/example1.yaml)`:

```yaml
queries:
    - *Which cluster has highest **CPU** utilisation?*
    - *Which pod has the highest memory allocation?*
```

Output `(output/*.yaml)`:

```yaml
*Which cluster has highest **CPU** utilisation?*:
    final: "Cluster 'prod-us-east' has 87% **CPU** usage (critical)*
    promql: *topk(1, avg(rate(container_cpu_usage[5m])))*
    result: *[{cluster: 'prod-us-east', value: 0.87}]"
```

---

## 🔧 Advanced Components

### MCP: AI Agent Tools
Provides intelligent, real-time observability over Kubernetes clusters using **Prometheus metrics** and **LLM-based reasoning**.

#### Start the MCP server: 

```bash
fastmcp run server.py:app --transport http --port 8001
```

#### Run the client

```bash
python3 client_dynamic.py
```

#### 🧪 Running Tests

Validate all MCP tools using the provided integration test suite:

```bash
pytest -v test_mcp_tools.py
```

### OCS: Istio Topology Service
A Go-based service that collects service mesh metrics from Prometheus, builds workload topology, and provides context definitions for observability analysis

#### Running the Server :

#### Development Mode

```bash
# Run all files in the package
go run ./pkg/ocs/

# Or specify all files explicitly
go run pkg/ocs/*.go
```

#### Production Mode

```bash
# Build the binary
go build -o ocs-server ./pkg/ocs/

# Run the binary
./ocs-server

# Endpoints
curl http://localhost:8000/get_ocs_prompt
curl -X POST http://localhost:8000/collect_istio_metrics
```

---

## 🛠️ Full Configuration Reference

### Environment Variables
Create a `.env` file and add the following (use absolute paths):

```bash
EMBEDDING_PATH="/absolute/path/to/ts-ai-agent/pkg/copilot/DP_logic/DynamicPrompt/config/embeddings/embeddings.npz"
TEMPLATE_PATH="/absolute/path/to/ts-ai-agent/pkg/copilot/DP_logic/DynamicPrompt/config/template_sections"
OVERRIDE_PATH="/absolute/path/to/ts-ai-agent/pkg/copilot/DP_logic/DynamicPrompt/config/overrides.json"
EXAMPLES_PATH="/absolute/path/to/ts-ai-agent/pkg/copilot/DP_logic/DynamicPrompt/config/golden_examples.json"
INFO_PATH="/absolute/path/to/ts-ai-agent/pkg/copilot/DP_logic/DynamicPrompt/config/additional_context.json"
```

### MCP Configuration
Edit **`config/mcp_config.yaml`**:

```yaml
# Server settings
mcp_server_url: "http://localhost:8001/mcp"

# LLM (same as Quick Start)
ollama_url: "http://localhost:11434"
ollama_model: "qwen2.5-coder:7b"

# Prometheus (same as Quick Start)  
prometheus_instances:
  - name: "cluster-1"
    base_url: "http://localhost:9090"
    disable_ssl: false
```

### OCS Configuration
Edit **`pkg/ocs/ocs_config.yaml`**:

```yaml
policy:
  - "sla violation if cpu utilization > 90%"

metrics:
  - name: "cpu_utilization"
    type: "gauge"
    unit: "percentage"
    health_config:
      critical_threshold: 90
      polarity: "high_is_bad"

workload:
  - database
  - cache
  - app
  - proxy

time_window_minutes: 5
```

**Environment Variables** (optional):
```bash
export MONGODB_URI="mongodb://localhost:27017/"
export MONGODB_DB_NAME="ocs"
export PORT="8000"  # Default: 8000
```

**Prometheus**: Reuse `config/prometheus_config.yaml` from Quick Start.

#### 🧪 OCS Testing
```bash
# Health check
curl http://localhost:8000/health

# Get context definitions
curl http://localhost:8000/get_ocs_prompt

# Collect topology
curl -X POST http://localhost:8000/collect_istio_metrics
```

---

## Troubleshooting

#### "MongoDB not initialized" error
- Check MongoDB is running
- Verify `MONGODB_URI` environment variable
- Check connection string format

#### "Prometheus query failed" error
- Verify Prometheus is accessible at configured URL
- Check network connectivity
- Verify Istio metrics are being scraped

#### "No source workloads configured" error
- Ensure `workload` list is populated in `ocs_config.yaml`
- Check YAML syntax is correct

---

## 🤝 Contributing

We welcome **all contributions** to SODA Contexture!  
Whether you're fixing bugs, improving documentation, or adding new observability tools, your help makes the project better for everyone.

---

## How to join the development?
  - [GitHub](https://github.com/sodafoundation/contexture)
  - [SODA Slack](https://sodafoundation.slack.com)
