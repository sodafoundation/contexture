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
   = Mixing guesses and different sources of knowledge confuses AI
- Inconsistency
   - Hallucination is key known issue with AI
- High Latency
  - Based on the type of query and volume of data, it fails to give ontime results
- Huge Cost
  - Iterations to get a close results and verification add costs
- Lack of Scale
  - Works for small amount of data or 1 agent, when it comes to scale, it fails
- Low Reliability
  = Due uncertain results AI is not fully dependable

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
  - This will avoid the AI comparing unrelated mertrics.
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

### How to join the development?
  - [GitHub](https://github.com/sodafoundation/contexture)
  - [SODA Slack](https://sodafoundation.slack.com)
  - [OCS RFC] (https://docs.google.com/document/d/1XHN8NuXTPqKWOikFALfCTZHt6JCDpsHS)


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