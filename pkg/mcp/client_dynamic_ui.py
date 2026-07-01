import asyncio
import json
import httpx
import re
import os
import yaml
import string
from fastmcp import Client
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime

app = FastAPI(title="Contexture Backend Service")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def load_config(path="config.yaml"):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r") as f:
        return yaml.safe_load(f)

# Load configurations
config_base = os.path.join(os.path.dirname(__file__), "../../config")
ollama_config = load_config(os.path.join(config_base, "ollama_config.yaml"))
server_config = load_config(os.path.join(config_base, "mcp_server_config.yaml"))

OLLAMA_API_URL = ollama_config.get("ollama_url")
MODEL_NAME = ollama_config.get("ollama_model")

# MCP clients — Prometheus (default) and ClickHouse
prometheus_mcp_client = Client(server_config.get("mcp_server_url", "http://localhost:8001/mcp"))
clickhouse_mcp_client = Client(server_config.get("clickhouse_mcp_url", "http://localhost:8004/mcp"))

def _get_mcp_client_for_tool(tool_name: str) -> Client:
    """Route tool calls: ch_* → ClickHouse MCP, everything else → Prometheus MCP."""
    if tool_name.startswith("ch_"):
        return clickhouse_mcp_client
    return prometheus_mcp_client

# Data Models
class QueryRequest(BaseModel):
    query: str
    context: Optional[str] = ""

class QueryResponse(BaseModel):
    summary: str
    results: List[Dict]
    workflow: List[Dict]
    ocs_input: str
    ocs_output: str
    timestamp: str

async def ask_ollama_stream(prompt: str):
    
    async with httpx.AsyncClient(timeout=None) as session:
        async with session.stream(
            "POST",
            f"{OLLAMA_API_URL}/v1/completions",
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "max_tokens": 1000,
                "temperature": 0.0,
                "stream": True
            },
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    chunk = line[6:]
                    if chunk != "[DONE]":
                        try:
                            data = json.loads(chunk)
                            text = data.get("choices", [{}])[0].get("text", "")
                            if text:
                                yield text
                        except json.JSONDecodeError:
                            continue

async def ask_ollama(prompt: str, history="") -> str:
    
    async with httpx.AsyncClient(timeout=300.0) as session:
        resp = await session.post(
            f"{OLLAMA_API_URL}/v1/completions",
            json={
                "model": MODEL_NAME,
                "prompt": prompt + str(history),
                "max_tokens": 1000,
                "temperature": 0.0
            }
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["text"]


# Returns only list (ocs_prompt is fetched separately in run_query)
async def llm_to_workflow(nl_query: str) -> list:
    print("Entering llm_to_workflow with query:", nl_query)

    # Use a local variable named http_client to avoid shadowing the global mcp_client
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        resp = await http_client.get("http://localhost:8000/get_ocs_prompt")
        resp.raise_for_status()
        ocs_prompt: str = resp.text   # <-- stored as string

    print("Fetched OCS context from the context provider")
    # print("OCS Prompt:", ocs_prompt)

    
    prompt = (
        "You are an assistant that converts natural language queries into a sequence of available MCP tool calls. "
        "Return ONLY JSON. Each step should include 'tool_name', 'params' (dictionary), "
        "arrange it in a logical flow of calls. Limit to a maximum of 4 calls when the user asks about full stack or all workloads (so you can cover policy + up to 3 workloads); otherwise maximum 3 calls, minimum 1 call.\n"
        "If there are params that can't be filled based on the info you have, make it empty string.\n\n"
        "Context specification from the context provider (JSON):\n"
        f"{ocs_prompt}\n\n"
        "Topology (hierarchy): Each context_definition may have a 'topology' object.\n"
        "- 'dependencies' = workloads this workload calls (downstream dependencies).\n"
        "- 'dependents' = workloads that call this workload (upstream callers).\n"
        "Example: frontend depends on backend, backend depends on db → for 'backend', dependencies=[db], dependents=[frontend].\n\n"
        "Composing workload calls:\n"
        "- When the user asks about a workload 'and its dependencies', 'stack', 'layer', 'chain', or 'and what it calls': "
        "call workload_metrics for that workload AND each of its topology.dependencies (in dependency order: leaf first, e.g. db then backend then frontend).\n"
        "- When the user asks about 'full stack', 'all layers', 'whole chain', or 'all workloads': "
        "call workload_metrics for each workload in dependency order (dependencies before dependents).\n"
        "- Use the specification's workload names and metrics; map synonyms (e.g. database, DB → db).\n\n"
        "If the user asks to explain/interpret policy (SLA, thresholds, what the policy means), include a call to explain_ocs_policy first.\n\n"
        "Available Tools:\n"
        "\n--- Prometheus / Kubernetes Tools ---\n"
        "- explain_ocs_policy(config_path: str = 'pkg/ocs/ocs_config.yaml', output_format: str = 'bullets')\n"
        "- workload_metrics(metric_name: str = 'container_cpu_utilization', workload_name: Optional[str] = None, pod_names: Optional[List[str]] = None, time_window: Optional[str] = None, aggregation: str = 'avg')\n"
        "- top_n_pods_by_metric(metric_name: str = 'container_cpu_usage_seconds_total', top_n: int = 5, window: str = '5m')\n"
        "- pods_exceeding_cpu(threshold: float = 0.8)\n"
        "- pods_exceeding_memory(threshold_bytes: float = 1073741824)\n"
        "- pod_status_summary()\n"
        "- node_disk_usage()\n"
        "- node_memory_usage()\n"
        "- describe_cluster_health()\n"
        "- top_disk_pressure_nodes(threshold: float = 80.0, top_n: int = 5)\n"
        "- top_memory_pressure_nodes(threshold: float = 80.0, top_n: int = 5)\n"
        "- pod_restart_trend(window: str = '30m', top_n: int = 5)\n"
        "- detect_pod_anomalies(metric_name='container_cpu_usage_seconds_total', z_threshold=3.0)\n"
        "- detect_crashloop_pods(window='10m', threshold=2)\n"
        "- pod_event_timeline(pod_name: str, window: str = '30m')\n"
        "- node_condition_summary()\n"
        "\n--- ClickHouse Database Tools (prefix: ch_) ---\n"
        "- ch_list_databases()\n"
        "- ch_list_tables(database: str = 'default')\n"
        "- ch_describe_table(database: str, table: str)\n"
        "- ch_execute_query(sql: str, limit: int = 100)\n"
        "- ch_get_table_stats(database: str, table: str)\n"
        "- ch_get_db_stats()\n"
        "- ch_get_slow_queries(min_duration_ms: float = 100.0, limit: int = 10)\n"
        "- ch_check_db_health()\n\n"
        f"Natural language query: {nl_query}"
    )
    llm_response = await ask_ollama(prompt)
    # print(llm_response)
    llm_response = re.sub(r"```(?:json)?", "", llm_response.strip())

    try:
        workflow = json.loads(llm_response)
        if not isinstance(workflow, list):
            workflow = [workflow]
        return workflow
    except json.JSONDecodeError:
        # fallback: single-step call
        return [{"tool_name": nl_query.strip(), "params": {}}]


async def execute_workflow(workflow: list) -> list:
    
    context = {}  
    results = []
    history = ""

    # Open both MCP client sessions
    async with prometheus_mcp_client:
      async with clickhouse_mcp_client:
        for step in workflow:

            print("Executing step:", step)

            tool_name = step.get("tool_name")
            params = step.get("params", {}).copy()

            # print(params.items())
            for k, v in params.items():
                if isinstance(v, str) and "{" in v:
                    try:
                        params[k] = string.Template(v).safe_substitute(context)
                    except Exception:
                        pass

            # Collect keys that need resolution BEFORE iterating to avoid mutation errors
            keys_to_resolve = []
            for k, v in params.items():
                if v is None or (isinstance(v, str) and v.strip() == "") or v == "" or v == []:
                    keys_to_resolve.append(k)

            for k in keys_to_resolve:
                print("Resolving param my making another call to LLM...")
                summary_prompt = f"Summarize these tool call results: {results}\nProvide a neat minimal summary."

                llm_value = await ask_ollama(summary_prompt, "")
                prompt = (
                    f"\nGiven the previous tool outputs, \n"
                    f"Read carefully and get the appropriate value from previous tool outputs for the workflow step for parameter {k}. Make sure the value is of correct type (str, int, list etc)"
                    "and return tool call only in JSON format. remove unnecessary characters and '\n', also make sure number of params is same as the workflow step \n"
                )
                llm_value = await ask_ollama(prompt, "Workflow Step: "+str(step) + " Previous tool results: "+str(llm_value))
                try:
                    # Try parsing JSON first; update only this key, don't replace the whole params dict
                    parsed_value = re.sub(r"```(?:json)?", "", llm_value.strip())
                    resolved_params = json.loads(parsed_value)
                    params[k] = resolved_params.get("params", {}).get(k, resolved_params)
                except json.JSONDecodeError:
                    # fallback: use raw text for this key only
                    params[k] = re.sub(r"```(?:json)?", "", llm_value.strip())

           
            try:
                print("Calling tool:", tool_name, "with params:", params)
                result = await _get_mcp_client_for_tool(tool_name).call_tool(tool_name, params)
            except Exception as e:
                result = {"error": str(e)}

            results.append({"tool_name": tool_name, "result": result})

    return results


async def run_query(nl_query: str) -> tuple:
    workflow = await llm_to_workflow(nl_query)
    print("Generated Workflow:", workflow)

    # Fetch ocs_prompt here so it's available for the summary prompt below
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        resp = await http_client.get("http://localhost:8000/get_ocs_prompt")
        resp.raise_for_status()
        ocs_prompt: str = resp.text

    results = await execute_workflow(workflow)
    # print("\nTool call results:")
    """for r in results:
        print(r)"""

    summary_prompt = (
        f"Summarize these tool call results: {results}\n"
        "Provide a neat minimal summary. Interpret using the context specification and its topology.\n"
        f"Context specification: {ocs_prompt}\n\n"
        "Rules:\n"
        "- Apply the policy in the specification to the results; only report an SLA violation when the metric value strictly exceeds the critical_threshold in the same unit (do not assume; compare numerically).\n"
        "- If the specification has 'topology' (dependencies/dependents), interpret results along the dependency chain: e.g. 'workload A depends on B'; if A is bad and B is good, note that the issue is likely in A; if B is bad, note that A may be affected by B.\n"
        "Do not assume values; analyse strictly with respect to the context specification."
    )
    full_summary = ""
    async for chunk in ask_ollama_stream(summary_prompt):
        print(chunk, end="", flush=True)
        full_summary += chunk
    
    print("\n")
    
    return full_summary, results


# FastAPI Endpoints

@app.get("/")
def root():
    return {"message": "Contexture Backend Service", "status": "running"}

@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.post("/api/query")
async def process_query(request: QueryRequest):
    """
    Process a natural language query and return results with OCS context
    """
    try:
        full_summary, results = await run_query(request.query)
        return {"summary": full_summary, "results": results, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/config")
def get_config():
    """Return current backend configuration"""
    return {
        "ollama_url": OLLAMA_API_URL,
        "model": MODEL_NAME,
        "mcp_server": server_config.get("mcp_server_url"),
        "status": "configured"
    }


if __name__ == "__main__":
    import uvicorn
    print("Starting Contexture Backend Service...")
    print(f"Ollama URL: {OLLAMA_API_URL}")
    print(f"Model: {MODEL_NAME}")
    print(f"MCP Server: {server_config.get('mcp_server_url')}")
    uvicorn.run(app, host="0.0.0.0", port=8002)
