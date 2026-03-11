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

### Local Development Setup (Docker Compose)
To quickly spin up a local development environment with all required components, you can use Docker Compose. This solves the issue of manually configuring Prometheus, MongoDB, Ollama, and the OCS Engine separately.

Run the following command from the repository root:
```bash
docker compose up -d
```

#### What does this do?
The docker-compose setup spins up the following services:
- **Prometheus** (Port `9090`): A time-series database and monitoring system. Used to scrape metrics.
- **MongoDB** (Port `27017`): Expected by the OCS engine for potential data storage operations. Starts with a database named `contexture`.
- **Ollama** (Port `11434`): A local implementation for LLM endpoints, required by the context engine.
- **OCS Engine** (Port `8000`): The core SODA Contexture Engine built from source (`pkg/ocs/main.go`).

#### OCS Engine Inputs and Outputs
The `ocs-engine` container exposes an HTTP server on port `8000` with the following key endpoints:

1. **Input**: `GET /get_ocs_prompt`
   - Collects OCS data and topology context to formulate a prompt for the AI agent to make inferences based on the fetched metrics.
2. **Input**: `POST /collect_istio_metrics`
   - Takes input to trigger data collection (e.g., from Prometheus) and parses it using the Open Context Specification to structure operational context.
3. **Output**: `GET /health`
   - Returns the health status of the context engine. Used to verify the system is up and running.

### Progress 
We are actively developing the project. So if you would like to join the design, OCS and other components, please join us!

### How to join the development?
  - [GitHub](https://github.com/sodafoundation/contexture)
  - [SODA Slack](https://sodafoundation.slack.com)
