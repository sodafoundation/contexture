<div align="center">
  <img src="https://sodafoundation.io/wp-content/uploads/2025/10/SODA_logo_outline_c.png" alt="SODA Foundation Logo" width="100"/>
  <p align="left">
    <br/>
    <b>SODA Contexture</b> is a new initiative by the SODA Foundation. <br/>
    The <b>SODA TS AI Agent</b> serves as the first prototype of this project, demonstrating our vision for intelligent data management.
  </p>
</div>

### Welcome to SODA Contexture
### 🚧 Status: Research & Development in Progress
We are currently in the active R&D phase, exploring new possibilities and building the foundations of Contexture. Things are moving fast, and we are excited about the road ahead!
### 🤝 Join Us!
We warmly welcome more contributors and partners to join us on this journey. Whether you are a developer, researcher, or organization interested in data management and AI, there is a place for you here.
- **Contribute**: Join the development of the SODA Contexture on [GitHub](https://github.com/sodafoundation/contexture)
- **Connect**: Have questions or want to get involved? Chat with us on Slack: [Join SODA Foundation Slack](https://sodafoundation.io/slack)
---
<div align="center">
  <sub>Part of the <a href="https://sodafoundation.io">SODA Foundation</a> ecosystem.</sub>
</div>


# SODA TS AI Agent is part of SODA Contexture Project. It is the first prototype developement and research.
---
# soda-ts-ai-agent

soda-ts-ai-agent is an open source AI agent for time series data
An initial implementation of the TSDB copilot to test multiple frameworks and their effect on the quality of answers. Currently using direct HTTP requests to the Prometheus endpoints with LLM generated PromQL, along with a dynamically generated prompt for each user query.

## 1. Prerequisites
### A running Time Series Database (TSDB) with accessible endpoints  
  - Currently, this project uses **Prometheus** as the TSDB backend  
  - Prometheus must be up and running, and its HTTP API endpoint should be available.

**Setting up Prometheus**
Follow the official Prometheus installation guide to get started:
(https://prometheus.io/docs/prometheus/latest/getting_started/)

### An available LLM served through Ollama  
- This project relies on Ollama to run large language models locally.  
- Install Ollama by following the instructions:
   (https://docs.ollama.com/linux)  
- Make sure the Ollama service is running (default endpoint: `http://127.0.0.1:11434`).  
- Model should be downloaded and running in Ollama.

## 2. Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Prepare Your Config

- **TSDB endpoint**: Set in `config/prometheus_config.yaml`
- **Ollama endpoint**: Set in `config/ollama_config.yaml`
- **Agent modes**: can be configured in `config/agent_modes.yaml`

## 4. Agent Modes
Currently we have
- `DYNAMIC_PROMPT`: Advanced prompt building with context and examples -> generate PromQL -> HTTP request to Prometheus endpoint
Any other modes like MCP or any other can be added.

## 5. Run CLI

#### Pre-requisite
Please follow the steps to configure Agent mode before running the cli.
- `DYNAMIC_PROMPT`: Follow [Configure DYNAMIC_PROMPT](#8-dynamic-prompt-mode)

#### Running the solution

```bash
python pkg/cli.py   --query-set test/query_sets/example1.yaml   --copilot DYNAMIC_PROMPT   --prometheus-config config/prometheus_config.yaml
```

## 6. Query Set Format

```yaml
queries:
  - "Which cluster has highest CPU utilisation?"
  - "Which cluster has the highest memory allocation?"
```

## 7. Output Format

Output is saved as YAML in the specified output directory.

```yaml
"Your question here":
  final: "Final human-readable summary or conclusion"
  ollama_response: "Detailed step-by-step reasoning or intermediate generation from LLM"
  promql: "raw PromQL query"
  result: "Output results of PromQL execution"
  error: "Optional error message if something went wrong"
```

Or on error:
```yaml
Which cluster has highest CPU utilisation in last month?:
  error: timed out
```

## 8. Dynamic Prompt Mode

To onboard domain knowledge for better prompts:

```bash
# To embed the mappings with current set of metrics available in prometheus.
curl <prometheus_url>/metrics > ./config/metrics.txt

python pkg/copilot/DP_logic/DynamicPrompt/onboarding_cli.py
```

It creates vector embeddings for metric context.

### **Important:** Update the following paths in your `.env` file:

```env
EMBEDDING_PATH=/Path to your/pkg/copilot/DP_logic/DynamicPrompt/config/embeddings/embeddings.npz
TEMPLATE_PATH=/Path to your/pkg/copilot/DP_logic/DynamicPrompt/config/template_sections
OVERRIDE_PATH=/Path to your/pkg/copilot/DP_logic/DynamicPrompt/config/overrides.json
EXAMPLES_PATH=/Path to your/pkg/copilot/DP_logic/DynamicPrompt/config/golden_examples.json
INFO_PATH=/Path to your/pkg/copilot/DP_logic/DynamicPrompt/config/additional_context.json
```
## Demo Videos
TS AI AGENT: https://www.youtube.com/watch?v=al3kg0OENMo